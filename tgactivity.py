from telethon import TelegramClient, tl, sync
import yaml
import time
import datetime
import schedule
import os.path
import sqlite3
import time
import sys
import math
import pytz

from PIL import Image, ImageDraw, ImageFont

CONFIG_FILE_NAME = 'config.yaml'
DATABASE_NAME = 'activity.db'
STATUS_OFFLINE = 'offline'
STATUS_ONLINE = 'online'

color_scheme = [
    (255,255, 255),
    (227, 242, 253),
    (187, 222, 251),
    (144, 202, 249),
    (100, 181, 246),
    (66, 165, 245),
    (33, 150, 243),
    (30, 136, 229),
    (25, 118, 210),
    (21, 101, 192),
    (13, 71, 161)
]

config = yaml.load(open(CONFIG_FILE_NAME))
interval = config['interval']

db = None

client = TelegramClient('activity_script', config['api_id'], config['api_hash']).start()

def init_database():
    global db
    db = sqlite3.connect(DATABASE_NAME)

    if not db_table_exists('activity'):
        print('Creating activity database table')
        db.execute('CREATE TABLE activity (group_id integer, timestamp integer, user_id integer, online boolean)')

    if not db_table_exists('users'):
        print('Creating users database table')
        db.execute('CREATE TABLE users (id interger, username text, first_name text, last_name text, PRIMARY KEY (id))')

    if not db_table_exists('dialogs'):
        print('Creating dialogs database table')
        db.execute('CREATE TABLE dialogs (id integer, title text, PRIMARY KEY(id))')


def db_table_exists(table_name):
    query = db.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', (table_name, ))
    return query.fetchone() is not None


def save_dialog_name(dialog_id, dialog_name):
    db.execute('INSERT OR IGNORE INTO dialogs (id, title) VALUES (?, ?)', (dialog_id, dialog_name))
    db.execute('UPDATe dialogs SET title = ? WHERE id = ?', (dialog_name, dialog_id))
    db.commit()


def record_user_activity(group_id, user_id, username, first_name, last_name, status):
    timestamp = round(time.time())

    # insert or update user info
    db.execute('INSERT OR IGNORE INTO users (id, username, first_name, last_name) VALUES(?, ?, ?, ?)', 
                (user_id, username, first_name, last_name))
    db.execute('UPDATE users SET username=?, first_name=?, last_name=? WHERE id=?',
                (username, first_name, last_name, user_id))

    # save activity info
    db.execute('INSERT INTO activity (group_id, timestamp, user_id, online) VALUES (?, ?, ?, ?)',
               (group_id, timestamp, user_id, status==STATUS_ONLINE))

    db.commit()


def get_user_status(user):
    time_now = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
    if type(user.status) == tl.types.UserStatusOnline:
        return STATUS_ONLINE
    elif hasattr(user.status, 'was_online'):
        seconds_diff = (time_now-user.status.was_online.replace(tzinfo=pytz.UTC)).total_seconds()
        if seconds_diff < interval:
            return STATUS_ONLINE
    return STATUS_OFFLINE


def process_statuses_for_chat(group_id):
    for user in client.iter_participants(client.get_entity(group_id)):
        if user.photo is not None:
            user_photo_path = 'photos/{}.png'.format(user.id)
            if not os.path.isfile(user_photo_path):
                name = user.first_name or ''
                name += ' ' + (user.last_name or '')
                print('Downloading profile photo of user', user.id, '(', name.strip(), ')')
                client.download_profile_photo(user, user_photo_path, download_big=True)
        record_user_activity(group_id, user.id, user.username, user.first_name, user.last_name, get_user_status(user))
    print(time.strftime('%H:%M', time.gmtime()), '-', 'Data for chat', group_id, 'saved')


def stats_job():
    print(time.strftime('%H:%M', time.gmtime()), '-', 'Running iteration')
    for dialog in client.get_dialogs():
        if dialog.title in config['target_groups']:
            save_dialog_name(dialog.entity.id, dialog.title)
            process_statuses_for_chat(dialog.entity.id)


def collect_data():
    print('Collecting chat activity data')
    init_database()
    stats_job()
    schedule.every(interval).seconds.do(stats_job)
    while True:
        schedule.run_pending()
        time.sleep(1)


def export_data():
    init_database()

    for row in db.execute('SELECT * FROM dialogs'):
        dialog_id, dialog_name = row
        print('Exporting heatmap for', dialog_name)
        export_heatmap_for_dialog(dialog_id, dialog_name)


def export_heatmap_for_dialog(dialog_id, dialog_name):
    # prepare data
    activity = {}

    for row in db.execute('SELECT timestamp, user_id, online FROM activity WHERE group_id = ?', (dialog_id,)):
        timestamp, user_id, online = row
        if user_id not in activity:
            activity[user_id] = {}
        record_day = datetime.datetime.fromtimestamp(timestamp).replace(hour=0, minute=0, second=0)
        record_time = timestamp - record_day.timestamp()
        interval_number = int(record_time % interval)
        if interval_number not in activity[user_id]:
            activity[user_id][interval_number] = (0, 0) # online, total
        online_intervals, total_intervals = activity[user_id][interval_number]
        total_intervals += 1
        if online == 1:
            online_intervals += 1
        activity[user_id][interval_number] = (online_intervals, total_intervals)

    # create a sorted list of users based on overall acitivty
    total_activity = {}
    users = []
    for user in activity:
        users.append(user)
        total_online = 0
        total_intervals = 0
        for data in activity[user].values():
            online_time, intervals = data
            total_online += online_time
            total_intervals += intervals
        total_activity[user] = float(total_online) / total_intervals
    users.sort(key=lambda x: -total_activity[x])
    
    # fonts
    header_font = ImageFont.truetype('fonts/Roboto/Roboto-Thin.ttf', 34)
    usernames_font_size = 16
    usernames_font = ImageFont.truetype('fonts/Roboto/Roboto-Regular.ttf', usernames_font_size)

    # export image
    img = Image.new('RGB', (1000, 800), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((8,8), dialog_name, (0,0,0), font=header_font)

    row_number = 0
    row_height = 40 # px
    for user_id in users:
        username, first_name, last_name = db.execute('SELECT username, first_name, last_name FROM users WHERE id =? LIMIT 1', (user_id,)).fetchone()
        display_name = ((first_name or '') + ' ' + (last_name or '')).strip() or ('@' + username)
        photo_path = 'photos/{}.png'.format(user_id)
        has_photo = os.path.exists(photo_path)
        if has_photo:
            user_photo = Image.open(photo_path, 'r')
            user_photo.thumbnail((row_height, row_height), Image.ANTIALIAS)
            img.paste(user_photo, (0, 50 + row_height*row_number))
        draw.text((row_height+8,50 + row_height*row_number + (row_height - usernames_font_size)/2), display_name, (0,0,0), font=usernames_font)
        
        # draw graph
        user_activity = activity[user_id]
        graph_width = 900
        total_intervals = int(24*60*60/interval)
        interval_width = graph_width / total_intervals
        for graph_index in range(total_intervals):
            if graph_index not in user_activity:
                continue
            current_offset = math.floor(graph_index*interval_width)
            current_width = math.floor((graph_index+1)*(interval_width)) - current_offset
            interval_online, interval_total = user_activity[graph_index]
            color_for_interval = color_scheme[min(math.floor(len(color_scheme)/interval_total*interval_online), len(color_scheme)-1)]
            draw.rectangle((row_height+150+current_offset, 50+row_height*row_number, row_height+150+current_offset+current_width, 50+row_height*(row_number+1)), color_for_interval, color_for_interval)
        row_number += 1

    # img.show()

    if not os.path.exists('export'):
        os.makedirs('export')
    img.save('export/{}.png'.format(dialog_id))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == 'export':
        export_data()
    else:
        collect_data()