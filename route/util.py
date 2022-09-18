import base64
from PIL import Image
from quart import websocket
import response
import os
import shutil
import telethon
import socketio
from telethon.sync import TelegramClient
import user.channel.message.util as message_utils
import user.channel.priority as priority_utils
from os import listdir
from os.path import isfile, join

api_id = 12655046
api_hash = 'd84ab8008abfb3ec244630d2a6778fc6'
client_list = dict()
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
session_list = dict()

# init server & set up variables


def init():
    load_session_file()

# auto load .session into client_list


def load_session_file():
    global api_id
    global api_hash
    global client_list
    global session_list
    sessionpath = "./"
    files = listdir(sessionpath)
    for f in files:
        fullpath = join(sessionpath, f)
        if isfile(fullpath) and f.split('.')[-1] == 'session':
            client = TelegramClient(f.split('.')[0], api_id, api_hash)
            print(client)
            client.connect()
            if client.is_user_authorized():
                print("session success: ", f)
                me = client.get_me()
                session_list[me.id] = f.split('.')[0]
                #  client_list[me.id] = client
            else:
                print("session failed: ", f)
            client.disconnect()


# determine the given phone is valid and return True if client login successfully
async def has_session(client, phone) -> bool:
    if not await client.is_user_authorized():
        try:
            await client.send_code_request(phone)
            return False
        except Exception as e:
            print(e)
            return False
    else:
        return True


async def make_folder(client_id) -> str:  # create user private folder
    path = f'./user/userid{client_id}'
    if not os.path.exists(path):
        os.makedirs(path)
        return ""
    else:
        return response.make_response("system", "Error making folder", 500)


async def delete_folder(client_id) -> str:  # delete user private folder
    path = f"./user/userid{client_id}"
    if not os.path.exists(path):
        return "Error deleting folder"
    else:
        shutil.rmtree(path, ignore_errors=True)
        return ""


async def get_profile_pic(client, client_id) -> str:
    # if the user has no photo, it will return None
    path = await client.download_profile_photo('me', os.path.join(os.getcwd(), f"user/userid{client_id}"))
    try:
        with open(path, 'rb') as file:
            raw_data = file.read()
            data = base64.b64encode(raw_data).decode()
        os.remove(path)
        return data
    except:
        return ""


# find the telethon Client instance
async def find_user(client_list, userID) -> telethon.client:
    global session_list
    userID = int(userID)
    if userID in client_list:
        return client_list[userID]
    elif userID in session_list:
        client = TelegramClient(session_list[userID], api_id, api_hash)
        await client.connect()
        client_list[userID] = client
        return client_list[userID]
    else:
        return None


def add_to_list(client_list, user_id, user):
    client_list[int(user_id)] = user


def remove_from_list(client_list, user_id):
    del client_list[int(user_id)]

# iterate through client's dialog and send unread message count back


async def send_unread_count(dialogs):
    """
    DEPRECATED
    MERGED WITH SEND PROFILE FUNCTION
    """
    x = []
    for d in dialogs:
        if(type(d.message.peer_id) == telethon.tl.types.PeerChannel):
            x.append([d.unread_count, d.message.peer_id.channel_id])
        elif(type(d.message.peer_id) == telethon.tl.types.PeerChat):
            x.append([d.unread_count, d.message.peer_id.chat_id])
        else:
            x.append([d.unread_count, d.message.peer_id.user_id])

    for e in x:
        unread = {
            "tag": "initial",
            "channel": e[1],
            "count": e[0]
        }
        # unread = str(unread).replace("\'", "\"")

        global sio
        await sio.emit('initial', unread)  # websocket.send(unread)


# iterate through dialog and send profile one by one
async def send_profile(dialogs, client, client_id):
    size = 64, 64
    for d in dialogs:
        if type(d.message.peer_id) == telethon.tl.types.PeerChannel:
            ID = d.message.peer_id.channel_id
        elif(type(d.message.peer_id) == telethon.tl.types.PeerChat):
            ID = d.message.peer_id.chat_id
        else:
            ID = d.message.peer_id.user_id
        path = f"./user/userid{client_id}/{ID}.png"
        message_list = await client.get_messages(d, 1)
        message = message_list[0]
        tag, context = await message_utils.context_handler(
            client_id, client, message)
        sender_id, sender = await message_utils.get_sender(message, client, d)

        if(sender_id is None):
            sender_id = ID

        # this might not download successfully if user has no profile
        await client.download_profile_photo(d, file=path, download_big=False)

        channel_pri = await priority_utils.retrive_prior(client_id, ID)
        try:
            # make thumbnail
            image = Image.open(path)
            image.thumbnail(size, Image.ANTIALIAS)
            thumbpath = f"./user/userid{client_id}/{ID}_thumb.png"
            image.save(thumbpath, "PNG")

            with open(thumbpath, "rb") as file:
                raw_data = file.read()
                b64 = base64.b64encode(raw_data).decode()
            os.remove(path)
            os.remove(thumbpath)
        except:
            b64 = "no profile"

        finally:
            obj = {
                "tag": "profile",
                "b64": b64,
                "channel": ID,
                "name": d.name,
                "priority": channel_pri,
                "last_message": {
                    "tag": tag,
                    "sender_id": sender_id,
                    "from": sender,
                    "data": context,
                    "message_id": message.id,
                    "time_stamp": str(message.date)
                },
                "unread_count": d.unread_count
            }

            global sio
            # websocket.send(str(obj).replace("\'", "\""))
            await sio.emit('initial', obj)
