## Idea: Given the link to a drive folder, the software must delete the similar images
## Note: To use it yourself all you've to do is maintain a .json file for your account which you can download from google cloud console 
## After downloading you've to specify the file name in line 102 which is maintained by variable "SERVICE_ACCOUNT_FILE"
from flask import Flask,render_template,request,url_for
import cv2 
import os
import io 
import glob
import google.auth
import hashlib
import shutil
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload,MediaIoBaseDownload

app=Flask(__name__)

def is_similar(image1, image2):
    # Create SIFT detector
    sift = cv2.SIFT_create()

    # Detect keypoints and compute descriptors for the two images
    kp1, desc1 = sift.detectAndCompute(image1, None)
    kp2, desc2 = sift.detectAndCompute(image2, None)

    # Create Brute-Force Matcher object
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)

    # Match descriptors of the two images
    matches = bf.match(desc1, desc2)

    # Sort the matches by distance
    matches = sorted(matches, key=lambda x: x.distance)

    # Calculate the average distance of the best matches
    num_best_matches = 10
    best_matches = matches[:num_best_matches]
    distances = [match.distance for match in best_matches]
    mean_distance = sum(distances) / len(distances)

    # If the average distance is less than a threshold value,
    # the images are considered similar
    threshold = 100
    if mean_distance < threshold:
        return True
    else:
        return False

def get_file_hash(filepath):
    with open(filepath, 'rb') as f:
        file_bytes = f.read()
        return hashlib.sha256(file_bytes).hexdigest()

def find_unique_images(folder_path, unique_folder_path):
    unique_images = []
    duplicate_images = []
    processed_images_hashes = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            file_hash = get_file_hash(file_path)

            # Skip the file if it has already been processed
            if file_hash in processed_images_hashes:
                continue

            image = cv2.imread(file_path)
            if image is None:
                continue

            if cv2.Laplacian(image, cv2.CV_64F).var() < 100:
                continue
            
            found_duplicate = False
            for unique_image in unique_images:
                if is_similar(image, unique_image):
                    duplicate_images.append(file_path)
                    found_duplicate = True
                    break

            if not found_duplicate:
                unique_images.append(image)
                unique_images.append(file_path)
                shutil.copy(file_path, unique_folder_path)

            # Add the processed file hash to the list
            processed_images_hashes.append(file_hash)

    # Save one image from each set of duplicate images
    for duplicate_image in duplicate_images:
        file_path = os.path.join(unique_folder_path, os.path.basename(duplicate_image))
        if not os.path.exists(file_path):
            shutil.copy(duplicate_image, unique_folder_path)
            
    return unique_images, duplicate_images

# Set the Google Drive API credentials
def delete_files(folder_id):
    SCOPES = ['https://www.googleapis.com/auth/drive']
    SERVICE_ACCOUNT_FILE = 'perfect-altar-385219-a8c83cb173e1.json'  # replace with the path to your service account credentials
    FOLDER_ID = folder_id  # replace with the ID of the folder you want to delete files from

    # Authenticate and build the Drive API client
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    # Get a list of all files in the specified folder
    query = f"'{FOLDER_ID}' in parents"
    results = service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    ## Downloading all files
    if not items:
        print('No files found.')
    else:
        print('Files:')
        for file in items:
            print(f'{file.get("name")} ({file.get("id")})')
            request = service.files().get_media(fileId=file.get("id"))
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print(f'Download {int(status.progress() * 100)}.')

            if not os.path.exists('downloads'):
                os.makedirs('downloads')
            # Save the downloaded file to a local directory
            with open(os.path.join('downloads', file.get('name')), 'wb') as f:
                f.write(file_content.getbuffer().tobytes())

    unique_folder_path = 'images/'
    if not os.path.exists(unique_folder_path):
        os.makedirs(unique_folder_path)

    unique_images, duplicate_images = find_unique_images('downloads/', unique_folder_path)
    print('Unique images:', len(unique_images) // 2)
    print('Duplicate images:', len(duplicate_images))

    # Create the new folder in Google Drive
    new_folder_name='SIFT'
    folder_metadata = {'name': new_folder_name, 'parents': [FOLDER_ID], 'mimeType': 'application/vnd.google-apps.folder'}
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    folder_id = folder.get('id')
    local_directory_path='images/'

    # Upload all files from the local directory to the new folder in Google Drive
    for filename in os.listdir(local_directory_path):
        file_metadata = {'name': filename, 'parents': [folder_id]}
        file_path = os.path.join(local_directory_path, filename)
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print('File ID: %s' % file.get('id'))

    return items
    
@app.route('/',methods=['GET'])
def home():
    return render_template('basic.html')   

@app.route('/',methods=['POST'])
def main():
    link=request.form['driveURL']
    link=delete_files(link)
    return render_template('basic.html',link=link)

if(__name__=="__main__"):
    app.run(debug=True)