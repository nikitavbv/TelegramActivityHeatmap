from telethon import TelegramClient, tl, sync
import yaml
import time
import datetime
import schedule
import os.path
import sqlite3
import time

CONFIG_FILE_NAME = 'config.yaml'
DATABASE_NAME = 'activity.db'
STATUS_OFFLINE = 'offline'
STATUS_ONLINE = 'online'

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
    time_now = datetime.datetime.utcnow()
    if type(user.status) == tl.types.UserStatusOnline:
        return STATUS_ONLINE
    elif hasattr(user.status, 'was_online'):
        seconds_diff = (time_now-user.status.was_online).total_seconds()
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


def stats_job():
    print(time.strftime('%H:%M', time.gmtime()), '-', 'Running iteration')
    for dialog in client.get_dialogs():
        if dialog.title in config['target_groups']:
            save_dialog_name(dialog.entity.id, dialog.title)
            process_statuses_for_chat(dialog.entity.id)


if __name__ == "__main__":
    init_database()
    stats_job()
    schedule.every(interval).seconds.do(stats_job)
    while True:
        schedule.run_pending()
        time.sleep(1)