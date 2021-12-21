# JunoCam Bot
# Developed by Christian Diaz
#
# All data and images are credited to the JunoCam team.
import requests 
import shutil
import time
from datetime import datetime
import re
import sys
import os
from zipfile import ZipFile
import tweepy
import random
import json
from dotenv import load_dotenv
import requests

load_dotenv()

if not os.path.isfile(".env"):
    print("Missing env file!  Please make an .env file with all 4 twitter API keys.")
    sys.exit()
if not os.path.isfile("current_num.txt"):
    f = open("current_num.txt", "w+")
    f.close()
    
# Authenticate to Twitter
auth = tweepy.OAuthHandler(os.getenv('CONSUMER_KEY'), os.getenv('CONSUMER_SECRET'))
auth.set_access_token(os.getenv('ACCESS_TOKEN'), os.getenv('ACCESS_TOKEN_SECRET'))

# Create API object
api = tweepy.API(auth)

# Current number the JunoCam dataset is at.
# This is used to get a starting point for the bot to start processing images.
current_num = input("Please enter the current number of junocam: ")
if int(current_num) == 0:
    f = open("current_num.txt", "r+")
    current_num = int(f.read())
    f.close()


def web_client(num):
    # Pings the JunoCam url and returns the response.
    response = requests.get(f"https://www.missionjuno.swri.edu/Vault/VaultDownload?VaultID={num}", stream=True)
    return response


def refresh_saved_images(*file):
    saved_image_names = []
    if file:
        with open("saved_image_names.txt", "r+") as file_handle:
            saved_image_names = [current_place.rstrip() for current_place in file_handle.readlines()]
        saved_image_names.append(file)
    else:
        if os.path.isdir("data"):
            for root, dirs, files in os.walk("data"):
                for image in files:
                    saved_image_names.append(image)
    with open('saved_image_names.txt', 'w') as filehandle:
        filehandle.writelines("%s\n" % image for image in saved_image_names)


def check_if_image_saved(image):
    saved_image_names = []
    with open("saved_image_names.txt", "r+") as file_handle:
            saved_image_names = [current_place.rstrip() for current_place in file_handle.readlines()]
    if image in saved_image_names:
        return True
    else:
        return False
    

def get_meta_data():
    # Returns metadata of selected image.
    attempts = 0
    # Determines if filename is correct (5 numbers with "Data" in the filename.)
    # If filename is correct, returns selected metadata from a dataset JSON file.
    while True:
        try:
            # DataSet JSONs are one number above the number of an ImageSet folder.
            response = web_client(current_num + 1)
            filename = get_filename_from_cd(response.headers.get('content-disposition'))
            # Removes quotes from filename
            filename = filename[1: -1]
            try:
                int(filename[0:4])
            except ValueError:
                print("No DataSet!")
                return None
            if "Data" in filename:
                # Gets the downloaded JSON and filename.
                file = save_zip(response, filename, "data")
                json_file = os.path.join("DataSet", file)
                with open(json_file) as e:
                    data = json.load(e)
                    # Selected metadata is formatted (used in status text.)
                    meta_data = {
                        "Instrument": data["INSTRUMENT_NAME"],
                        "Time": data["IMAGE_TIME"],
                        "PJ": data["PJ"],
                        "Target": data["TARGET_NAME"],
                        "Credit": data["PRODUCER_ID"]
                    }
                    e.close()
                    # Saves JSON to permanent data folder.
                    if not os.path.isdir("data/dataset_files"):
                        os.makedirs("data/dataset_files")
                    new_json_file = os.path.join("data/dataset_files", file)
                    shutil.copyfile(json_file, new_json_file)
                    shutil.rmtree("DataSet")  # Removes temp dataset folder and JSON
                    return meta_data
            else:
                print("Not a data file!")
                return None
        except requests.exceptions.Timeout:
            attempts += 1
            print('timeout!')
        except requests.HTTPError or urllib3.exceptions:
            attempts += 1
            print("bad!")
        except Exception as e:
            print(f"t) Error {e} occurred, aborting...")
            time.sleep(30)
        if attempts >= 3:
            return None


def tweet_image(file):
    d = get_meta_data()  # Metadata for status
    if d is None:
        status = "No metadata available."
    else:
        status = (f"Perijove {d['PJ']}: {d['Instrument']}, taken at {d['Time']}, Target: {d['Target']} (Image credit: {d['Credit']})")
    attempts = 0
    while True:
        if d is None:
            print(f"No metadata for {current_num}")
            break
        try:
            # Tweets image with metadata
            upload_result = api.media_upload(filename=file, chunked=True)
            metadata = {"media_id": upload_result.media_id_string,
                        "alt_text": {
                            "text": status,
                            }
                        }
            print(metadata)
            try:
                requests.post(url="https://upload.twitter.com/1.1/media/metadata/create.json", data=metadata)
            except Exception as e:
                print("oh dear")
                print(e)
            api.update_status(status=status, media_ids=[upload_result.media_id_string], chunked=True)
            print(f"Tweeted at {time.time()}!")
            break
        except Exception as e:
            # Sleeps if error occurred, sleeps longer with more attmepts, and eventually aborts after 3 failed attempts.
            print(f"Encountered error: {e}. ATTEMPTS: {attempts}")
            if attempts >= 3:
                print("Aborting tweet...")
                break
            attempts += 1
            time.sleep(15 * attempts)


def write_image(filename):
    # Creates data path for images
    if not os.path.isdir("data"):
        os.mkdir("data")
    else:
        # Naive method of checking if image has already been tweeted.
        # TODO: store and check media IDs 
        image_saved = check_if_image_saved(filename)
        if image_saved == True:
            print("Image has already been sent.")
            return False
        else:
            pass

    raw_file = os.path.join("ImageSet", filename)
    if os.path.getsize(raw_file) >= 4882999:
        print("File too big, aborting image.")
        return False
    # Creates path for file based on the date of the image.
    file_date = datetime.strptime(filename[5:12], "%Y%j")
    str_date = file_date.strftime("%Y/%j")
    full_path = os.path.join("data", str_date)
    if not os.path.isdir(full_path):
        os.makedirs(full_path)
    final_file = os.path.join(full_path, filename)
    # Copys temp image to data folder
    shutil.copyfile(raw_file, final_file)
    shutil.rmtree("ImageSet")  # Deletes temp imageset folder and image
    print('Successfully saved image!')
    refresh_saved_images(filename)
    tweet_image(final_file)
    return True


def save_zip(data, filename, mode):
    # Gets downloaded Zip and extracts it.
    open(filename, 'wb').write(data.content)
    with ZipFile(filename, 'r') as zipObj:
        # Extract all the contents of zip file in current directory
        zipObj.extractall()
    os.remove(filename)  # Removes zip file
    # Only for image zip files
    if mode == "image":
        files = os.listdir("ImageSet")

        image = False
        for file in files: 
            # "mapprojected" is a stacked RGB image
            if "mapprojected" in file:
                image = write_image(file)
        if image is False:
            for file in files: 
                if "raw" in file:
                    image = write_image(file)
        if image is False:
            print("No image found in dataset, aborting this imageset...")
            return False
        
    # Data zip files
    if mode == "data":
        # Returns last file in dataset folder
        files = os.listdir("DataSet")
        return files[-1]


def get_filename_from_cd(cd):
    """
    Get filename from content-disposition
    """
    if not cd:
        return None
    fname = re.findall('filename=(.+)', cd)
    if len(fname) == 0:
        return None
    return fname[0]


attempts = 0
refresh_saved_images()
while True:
    file = open("current_num.txt", "w")
    file.write(str(current_num))
    file.close()
    
    # x is the multiplier applied to the sleep period.
    x = 60
    try:
        # Pings the the JunoCam url with the current number.  It will continously 
        print(f"Current iteration: {current_num}")
        response = web_client(current_num)
        filename = get_filename_from_cd(response.headers.get('content-disposition'))
        if filename == None:
            # If no filename (no file) is found, we are at the current last object in the JunoCam dataset.
            print("We are at the end of the image queue.")
        else:
            # Removes quotes from filename
            filename = filename[1: -1]
            try:
                # Determines if filename is correct (5 numbers with "ImageSet" in the filename.)
                # If filename is correct, returns selected zip file to be used for prcoessing.
                # If not correct, the program will skip the number and move onto the next object in the JunoCam dataset.
                int(filename[0:4])
                if "ImageSet" in filename:
                    save_zip(response, filename, "image")
                    x = 1
                    current_num += 4
                else:
                    # Can be DataSet file, which is only used later.
                    # Not imageset (move to next image.)
                    print("Not an image set!")
                    x = 1
                    current_num += 1

            except ValueError:
                # First 5 characters are not digits.
                # Not imageset (move to next image.)
                print("Not an image set!")
                x = 1
                current_num += 1
        
    except requests.exceptions.Timeout:
        attempts += 1
        print('timeout!')
    except requests.HTTPError or urllib3.exceptions:
        attempts += 1
        print("bad!")
    except Exception as e:
        print(f"j) Error {e} occurred, aborting...")
        time.sleep(30)
    if attempts >= 3:
        current_num += 1
        attempts = 0

    # Sleeps for a random time between a range.
    sleep_time = random.randrange(15 * x, 30 * x)
    print(f"Sleeping for {sleep_time} seconds.")
    time.sleep(sleep_time)
