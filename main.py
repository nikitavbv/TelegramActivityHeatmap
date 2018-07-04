from telethon import TelegramClient, tl, sync
import yaml
import time
import datetime
import schedule
import os.path
import sqlite3

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
        db.execute('CREATE TABLE activity (group_id integer, user_id integer, online boolean)')

    if not db_table_exists('users'):
        print('Creating users database table')
        db.execute('CREATE TABLE users (id interger, username text, first_name text, last_name text)')


def db_table_exists(table_name):
    query = db.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', (table_name, ))
    return query.fetchone() is not None


def record_user_activity(group_id, user_id, username, first_name, last_name, status):
    print(group_id, user_id, username, first_name, last_name, status)


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
        record_user_activity(group_id, user.id, user.username, user.first_name, user.last_name, get_user_status(user))


def stats_job():
    print(time.strftime('%H:%M', time.gmtime()), '-', 'Running iteration')
    for dialog in client.get_dialogs():
        if dialog.title in config['target_groups']:
            process_statuses_for_chat(dialog.entity.id)


if __name__ == "__main__":
    init_database()
    stats_job()
    schedule.every(interval).seconds.do(stats_job)
    while True:
        schedule.run_pending()
        time.sleep(1)