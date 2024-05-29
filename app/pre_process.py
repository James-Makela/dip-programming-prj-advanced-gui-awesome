from utils import get_vid_save_path, update_user_video_data, get_video_data
import cv2
from PIL import Image
import pytesseract
from remotellama import LlamaInterface
from utils import config


def run_ocr(ret, frame):
    temp_frame = frame
    if ret is True:
        cv2.imwrite('temp.png', temp_frame)
        return pytesseract.image_to_string(Image.open('temp.png'))
    else:
        return None


def formatted_prompt(extracted_text: str, language: str) -> str:
    return f"Analyse the following {language} code snippet:\n\n{extracted_text}\n\n" \
        f"If no '{language}' code is present, say 'No Code' and disregard the remaining prompt. Otherwise if"\
        f"'{language}' code is detected: If The Code is incomplete or has errors then prefix with 'Incomplete Code'" \
        f"correct any indentation errors, but do not add any code that does not exist in the sample and make sure to" \
        f"preserve comments" \
        f"Do NOT embellish the code, simply return the code as a codeblock or 'No Code'"


def seconds_to_timestamp(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"[{minutes:02}:{seconds:02}]"


def process_video(video_file_name, socketio):
    print(f"Processing video {video_file_name}")
    cap = cv2.VideoCapture(get_vid_save_path() + video_file_name)
    if not cap.isOpened():
        print("Error opening video file")

    # while the video is not finished
    video_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = int(cap.get(cv2.CAP_PROP_FPS))
    step_seconds = 1
    steps_with_code = []
    video_length_seconds = video_length // video_fps
    was_last_step_code = False
    update_user_video_data(video_file_name, None, None, False, True)
    while step_seconds < video_length_seconds:
        print(f"{seconds_to_timestamp(step_seconds)}/{seconds_to_timestamp(video_length_seconds)}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, step_seconds * video_fps)
        text = run_ocr(*cap.read())
        prompt = formatted_prompt(text, config("UserSettings", "programming_language"))
        response = LlamaInterface.query(prompt)
        if "```" in response:
            response = response.split("```")[2]
        print(response)

        if "No Code" not in response and step_seconds not in steps_with_code:  # Did we find code?
            dictEntry = {'timestamp': step_seconds, 'capture_content': response}
            update_user_video_data(video_file_name, None, dictEntry)
            steps_with_code.append(step_seconds)
            socketio.emit('update_timestamps', data=video_file_name)
            if not was_last_step_code:  # If we didn't find code last time, we want to skip back a bit
                step_seconds -= 4
            else:  # If we did find code last time, we want to skip forward a bit
                step_seconds += 1
            was_last_step_code = True
        else:  # We didn't find code skip forward
            step_seconds += 5
            was_last_step_code = False
    update_user_video_data(video_file_name, None, None, True, False)


def format_user_data(video_file_name, timestamp, dictEntry):
    """
    Update user video data with new capture, ensuring sorted by timestamp and no duplicates
    :param video_file_name: The name of the video file
    :param timestamp: The timestamp of the capture
    :param dictEntry: The capture data to be added
    """
    timestamp = timestamp

    video_data = get_video_data(video_file_name)

    # If the video is processed, do not update the captures
    if video_data.get('processed', True):
        return

    # Remove existing entry with the same timestamp if it exists
    video_data['captures'] = [capture for capture in video_data['captures'] if capture.get('timestamp') != timestamp]

    # Add the new capture entry
    video_data['captures'].append(dictEntry)

    # Sort captures by timestamp
    video_data['captures'].sort(key=lambda x: x['timestamp'])

    # Save updated video data
    update_user_video_data(video_file_name, timestamp, video_data)
