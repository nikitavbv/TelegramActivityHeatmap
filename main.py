from telethon import TelegramClient, tl
import yaml
import time
import datetime
import schedule
import os.path

CONFIG_FILE_NAME = 'config.yaml'
STATUS_OFFLINE = 'offline'
STATUS_ONLINE = 'online'

config = yaml.load(open(CONFIG_FILE_NAME))
interval = config['interval']

client = TelegramClient('activity_script', config['api_id'], config['api_id'])
client.start()

def record_user_activity(group_id, user_id, username, first_name, last_name, status):
    # save it to file
    pass

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
    dialogs = client.get_dialogs()
    for dialog in dialogs:
        if dialog.title in config['target_groups']:
            process_statuses_for_chat(dialog.entity.id)


if __name__ == "__main__":
    stats_job()
    schedule.every(interval).seconds.do(stats_job)
    while True:
        schedule.run_pending()
        time.sleep(1)