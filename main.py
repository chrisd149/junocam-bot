# JunoCam Bot
# Developed by Christian Diaz
#
# All data and images are credited to the JunoCam team.
import requests 
import shutil
import time
from datetime import datetime
import re
import os
from zipfile import ZipFile
import tweepy
import random
import json
from dotenv import load_dotenv

load_dotenv()

# Authenticate to Twitter
auth = tweepy.OAuthHandler(os.getenv('CONSUMER_KEY'), os.getenv('CONSUMER_SECRET'))
auth.set_access_token(os.getenv('ACCESS_TOKEN'), os.getenv('ACCESS_TOKEN_SECRET'))

# Create API object
api = tweepy.API(auth)

# Current number the JunoCam dataset is at.
# This is used to get a starting point for the bot to start processing images.
current_num = int(input("Please enter the current number of junocam: "))


def web_client(num):
    # Pings the JunoCam url and returns the response.
    response = requests.get(f"https://www.missionjuno.swri.edu/Vault/VaultDownload?VaultID={num}", stream=True)
    return response


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
            int(filename[0:4])
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
            print(f"Error {e} occurred, aborting...")
            time.sleep(900)
        if attempts >= 3:
            return None


def tweet_image(file):
    d = get_meta_data()  # Metadata for status
    if d is None:
        status = "Could not retrieve metadata"
    else:
        status = (f"Perijove {d['PJ']}: {d['Instrument']}, taken at {d['Time']}, Target: {d['Target']} (Image credit: {d['Credit']})")
    attempts = 0
    while True:
        try:
            # Tweets image with metadata
            upload_result = api.media_upload(filename=file)
            api.update_status(status=status, media_ids=[upload_result.media_id_string])
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
    raw_file = os.path.join("ImageSet", filename)
    if not os.path.isdir("data"):
        os.mkdir("data")

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
    if os.stat(final_file).st_size >= 4882000:
        print("Image is too big to upload to Twitter, aborting tweet...")
        return 
    else:
        tweet_image(final_file)


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
                write_image(file)
                image = True
        if image is False:
            # if no map projected images are found, we used the raw image.
            for file in files: 
                if "raw" in file:
                    write_image(file)
                    image = True
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
while True:
    # x is the multiplier applied to the sleep period.
    x = 15
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

            try:
                api.update_profile(description=f"A bot that tweets recent public images from the JunoCam team, taken from the Juno spacecraft in orbit around Jupiter. Built by @chrisd149. Current Num: {current_num}")
            except Exception as e:
                # Sleeps if error occurred, sleeps longer with more attmepts, and eventually aborts after 3 failed attempts.
                print(f"Encountered error: {e}.")
        
    except requests.exceptions.Timeout:
        attempts += 1
        print('timeout!')
    except requests.HTTPError or urllib3.exceptions:
        attempts += 1
        print("bad!")
    except Exception as e:
        print(f"Error {e} occurred, aborting...")
        time.sleep(900)
    if attempts >= 3:
        current_num += 1
        attempts = 0

    # Sleeps for a random time between a range.
    sleep_time = random.randrange(60 * x, 120 * x)
    print(f"Sleeping for {sleep_time} seconds.")
    time.sleep(sleep_time)
