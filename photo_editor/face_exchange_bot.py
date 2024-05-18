TELEGRAM_TOKEN = "None"

BOT_USERNAME = "None"

import asyncio
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext, Updater

from PIL import Image
from io import BytesIO
import os
import subprocess
import time
import shutil
import glob
import datetime
import queue
import threading

import logging

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

user_images = {}
request_queue = asyncio.Queue()
queue_positions = {}
queue_lock = asyncio.Lock()


# Define the /start command handler
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Welcome to the Face Swapping Bot (Developed by Sayantan)! Please send me the source image.")


# Define the image processing function
async def process_images(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    # Get the photo sent by the user
    photo = await update.message.photo[-1].get_file()

    user_dir = f"userdata/{user_id}"
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    user_images[user_id] = user_images.get(user_id, 0) + 1

    num_images = len(os.listdir(user_dir))

    # Save the photo locally
    filename = f"{user_dir}/{user_id}_{user_images[user_id]}.jpg"
    
    # Download the photo
    photo_bytes = await photo.download_as_bytearray()
    image = Image.open(BytesIO(photo_bytes))
    image.save(filename)

    if user_images[user_id] == 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Source image received! Please send me the target image.")

        print(f"Received images for {user_id}: {user_images[user_id]}")
    elif user_images[user_id] == 2:
        print(f"Received images for {user_id}: {user_images[user_id]}")

        ###############
        async with queue_lock:
            if user_id not in queue_positions:
                queue_positions[user_id] = request_queue.qsize() + 1
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Target image received! You are in queue position {queue_positions[user_id]}. Please wait...")
                await request_queue.put((user_id, chat_id))
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"You have already sent the target image and are in the queue. Please wait...")
        ###############
    
    elif len(os.listdir(user_dir)) > 2:
        await update.message.reply_text("Something went wrong. Please start again...")
        delete_images(user_id)
        

def delete_images(user_id):
    user_dir = f"userdata/{user_id}"
    if len(os.listdir(user_dir)) > 0:
        files = glob.glob(f"{user_dir}/*")
        for f in files:
            print(f)
            os.remove(f)
    del user_images[user_id]

def copy_data(user_id, chat_id):

    now = str(datetime.datetime.now())[10:19]
    now = now.replace(":","_")

    user_dir = f"userdata/{user_id}"

    ## Copy source
    src_dir = f"{user_dir}/{user_id}_1.jpg"
    backup_dir = f"backup_dir/{now}_source_{user_id}_{chat_id}.jpg"
    shutil.copy(src_dir, backup_dir)

    ## Copy target
    tgt_dir = f"{user_dir}/{user_id}_2.jpg"
    backup_dir = f"backup_dir/{now}_target_{user_id}_{chat_id}.jpg"
    shutil.copy(tgt_dir, backup_dir)

async def face_swap(user_id, face=0, face_enhancer=False):

    user_dir = f"userdata/{user_id}"
    processed_image_path = f"{user_dir}/{user_id}_processed_image.jpg"

    # Load the images
    source = f"{user_dir}/{user_id}_1.jpg"
    target = f"{user_dir}/{user_id}_2.jpg"

    if face_enhancer:
        cmd = f"-s '{source}' -t '{target}' -o {processed_image_path}  --keep-frames --keep-fps --execution-provider cpu --frame-processor  'face_swapper' 'face_enhancer' --reference-face-position {face}"
    else:
        cmd = f"-s '{source}' -t '{target}' -o {processed_image_path}  --keep-frames --keep-fps --execution-provider cpu --frame-processor  'face_swapper' --reference-face-position {face}"
    subprocess.Popen(f"python run.py {cmd}", shell=True).wait()

    time.sleep(1)

    return processed_image_path

# Define the function to process user images
def process_user_images(user_id, image_paths):
    # Load the images
    source = f"userdata/{user_id}_1.jpg"
    target = f"userdata/{user_id}_2.jpg"


    # Example processing: Combine the images
    processed_image = Image.blend(Image.open(source), Image.open(target), alpha=0.5)

    # Save the processed image
    processed_image_path = f"userdata/{user_id}_processed_image.jpg"
    processed_image.save(processed_image_path)

    return processed_image_path

# Function to process images from the queue
async def process_queue(bot):
    while True:
        user_id, chat_id = await request_queue.get()

        async with queue_lock:
            queue_positions.pop(user_id, None)

        # # Process the images
        # processed_image = process_user_images(user_images[user_id])
        processed_image_path = await face_swap(user_id)

        # Send the processed image back to the user
        await bot.send_photo(chat_id=chat_id, photo=open(processed_image_path, 'rb'))

        ## For backup
        copy_data(user_id, chat_id)

        # Clean up: delete saved images
        delete_images(user_id)

        request_queue.task_done()

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    bot = application.bot

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, process_images))
    
    # Get the current event loop
    loop = asyncio.get_event_loop()

    loop.create_task(process_queue(bot))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

