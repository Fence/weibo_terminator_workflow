# -*- coding: utf-8 -*-
# file: scrap.py
# author: JinTian
# time: 10/05/2017 10:38 PM
# Copyright 2017 JinTian. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------
import os
import time
import pickle
from tqdm import tqdm
from utils.connection import *
from utils.cookies import get_cookie_from_network
from settings.config import *
from settings.accounts import accounts
from scraper.weibo_scraper import WeiBoScraper


def set_accounts_cookies():
    if os.path.exists(COOKIES_SAVE_PATH):
        pass
    else:
        for account in accounts:
            print('preparing cookies for account {}'.format(account))
            get_cookie_from_network(account['id'], account['password'])
        print('all accounts getting cookies finished. starting scrap..')


def get_account_cookies(account):
    """
    get account cookies
    :return:
    """
    try:
        with open(COOKIES_SAVE_PATH, 'rb') as f:
            cookies_dict = pickle.load(f)
        print('\ncookies dict: {}\n'.format(cookies_dict))
        return cookies_dict[account]
    except Exception as e:
        print('Raise error in get_account_cookies, error:',e)
        return None


def scrap(scrap_id):
    """
    scrap a single id
    :return:
    """
    set_accounts_cookies()
    account_id = accounts[0]['id']
    cookies_error_flag = True
    error_count = 0
    error_page = -1

    while cookies_error_flag:
        try:
            cookies = get_account_cookies(account_id)
            scraper = WeiBoScraper(account_id, scrap_id, cookies, error_page)
            finish_flag = scraper.crawl()
            if finish_flag:
                break
        except AccountBanned as e:
            error_count += 1
            error_page = scraper.error_page
            print('\n\nA cookies-error occurred, the account has probably been banned.\
              \nNow will rest 10 mins to wait for release.')
            print('Ban error: {}\t self.rest_page: {} '.format(error_count, scraper.rest_page))
            localtime = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()))
            print('Current time: {}\n\n'.format(localtime))
            for i in tqdm(range(600)):
                time.sleep(1)
        except CookiesOutdated as e:
            print(e.msg)
            os.system('rm '+COOKIES_SAVE_PATH)
            set_accounts_cookies()
            if not os.path.exists(COOKIES_SAVE_PATH):
                print('\n\nAttention: no proper cookies, the program will exit.\n\n')
                exit()


def main(args):
    scrap_id = args
    scrap(scrap_id)
