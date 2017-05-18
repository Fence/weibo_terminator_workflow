# -*- coding: utf-8 -*-
# file: sentence_similarity.py
# author: JinTian
# time: 24/03/2017 6:46 PM
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
"""
using guide:
setting accounts first:

under: weibo_terminator/settings/accounts.py
you can set more than one accounts, WT will using all accounts one by one,
if one banned, another will move on.

if you care about security, using subsidiary accounts instead.

"""
import re
import os
import time
import pickle
import requests
import numpy as np
from lxml import etree
from settings.config import *
from utils.connection import *


class WeiBoScraper(object):

    def __init__(self, using_account, scrap_id, cookies, error_page, filter_flag=0):
        self.using_account = using_account
        self.cookies = cookies
        self.error_page = error_page

        self._init_cookies()
        self._init_headers()

        self.scrap_id = scrap_id
        self.filter = filter_flag
        self.user_name = ''
        self.weibo_num = 0
        self.weibo_scraped = 0
        self.following = 0
        self.followers = 0
        self.weibo_content = []
        self.num_zan = []
        self.num_forwarding = []
        self.num_comment = []
        self.weibo_detail_urls = []
        self.rest_time = 20
        self.rest_min_time = 20  # create random rest time
        self.rest_max_time = 30
        self.rest_page = 5
        self.rest_min_page = 5   # create random number for continuous pages
        self.rest_max_page = 10
        self.raise_error_page = 20
        self.jump_error_page = -1

        self.weibo_content_save_file = os.path.join(CORPUS_SAVE_DIR, 'weibo_content.pkl')
        self.weibo_content_and_comment_save_file = os.path.join(
            CORPUS_SAVE_DIR, 'weibo_content_and_comment.pkl')
        self.weibo_fans_save_file = os.path.join(CORPUS_SAVE_DIR, 'weibo_fans.txt')
        self.big_v_ids_file = os.path.join(CORPUS_SAVE_DIR, 'big_v_ids.txt')

    def _init_cookies(self):
        cookie = {
            "Cookie": self.cookies
        }
        self.cookie = cookie

    def _init_headers(self):
        """
        avoid span
        :return:
        """
        headers = requests.utils.default_headers()
        user_agent = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko/20100101 Firefox/11.0'
        }
        headers.update(user_agent)
        print('headers: ', headers)
        self.headers = headers

    def jump_scraped_id(self):
        """
        check mark scrapd ids, jump scraped one.
        :return:
        """
        if os.path.exists(SCRAPED_MARK):
            with open(SCRAPED_MARK) as f:
                scraped_ids = f.read().split('\n')
            if self.scrap_id in scraped_ids:
                return True
            else:
                return False
        else:
            return False

    def crawl(self):
        # this is the most time-cost part, we have to catch errors, 
        # return to dispatch center
        if self.jump_scraped_id():
            print('scrap id {} already scraped, directly pass it.'.format(self.scrap_id))
            return True
        else:
            try:
                self._get_html()
                self._get_user_name()
                self._get_user_info()

                self._get_fans_ids()
                self._get_weibo_content()
                self._get_weibo_content_and_comment()
                self.mark_as_scraped(self.scrap_id)
                return True
            except CookiesOutdated as e:
                print('\nRaise Exception in crawl, error:', e.msg)
                raise CookiesOutdated()
            except AccountBanned as e:
                print('\nRaise Exception in crawl, error:', e.msg)
                raise AccountBanned()
            except Exception as e:
                print('Raise Exception in crawl, error:', e)
                print('Some error above not catch, return to dispatch center, \
                    \nresign for new account..')

    def _get_html(self):
        try:
            url = 'http://weibo.cn/%s?filter=%s&page=1' % (self.scrap_id, self.filter)
            print(url)
            self.html = requests.get(url, cookies=self.cookie, headers=self.headers).content
            print('success load html..')
        except Exception as e:
            print('Raise Exception in _get_html, error:', e)

    def _get_user_name(self):
        print('\n' + '-'*30)
        print('getting user name')
        try:
            selector = etree.HTML(self.html)
            self.user_name = selector.xpath('//table//div[@class="ut"]/span[1]/text()')[0]
            print('current user name is: {}'.format(self.user_name))
        except Exception as e:
            print('Raise Exception in _get_user_name, error:', e)
            print('html not properly loaded, maybe cookies out of date or account being banned.\nIf so, change an account please')
            raise AccountBanned()

    def _get_user_info(self):
        print('\n' + '-' * 30)
        print('getting user info')
        selector = etree.HTML(self.html)
        pattern = r"\d+\.?\d*"
        str_wb = selector.xpath('//span[@class="tc"]/text()')[0]
        guid = re.findall(pattern, str_wb, re.S | re.M)
        for value in guid:
            num_wb = int(value)
            break
        self.weibo_num = num_wb

        str_gz = selector.xpath("//div[@class='tip2']/a/text()")[0]
        guid = re.findall(pattern, str_gz, re.M)
        self.following = int(guid[0])

        str_fs = selector.xpath("//div[@class='tip2']/a/text()")[1]
        guid = re.findall(pattern, str_fs, re.M)
        self.followers = int(guid[0])
        print('current user all weibo num {}, following {}, followers {}'.format(
            self.weibo_num, self.following, self.followers))


    def _get_fans_ids(self):
        """
        this method will execute to scrap scrap_user's fans,
        which means every time you scrap an user, you will get a bunch of fans ids,
        more importantly, in this fans ids have no repeat one.

        BEWARE THAT: this method will not execute if self.followers < 200, 
        you can edit this value.
        :return:
        """
        print('\n' + '-' * 30)
        print('getting fans ids...')
        if os.path.exists(self.big_v_ids_file):
            with open(self.big_v_ids_file) as f:
                big_v_ids = f.read().split('\n')
                if self.scrap_id in big_v_ids:
                    print('Fans ids of big_v {} (id {}) have been saved before.'.format(
                        self.user_name, self.scrap_id))
                    return
        print('total followers of {} : {}'.format(self.user_name, self.followers))
        if self.followers < 200:
            pass
        else:
            fans_ids = []
            if os.path.exists(self.weibo_fans_save_file):
                with open(self.weibo_fans_save_file) as f:
                    fans_ids = f.read().split('\n')

            fans_url = 'https://weibo.cn/{}/fans?'.format(self.scrap_id)
            # first from fans html get how many page fans have
            # beware that, this
            print(fans_url)
            html_fans = requests.get(fans_url, cookies=self.cookie, headers=self.headers).content
            selector = etree.HTML(html_fans)
            try:
                if not selector.xpath('//input[@name="mp"]'):# is None:
                    page_num = 1
                else:
                    page_num = int(selector.xpath('//input[@name="mp"]')[0].attrib['value'])
                print('all fans have {} pages.'.format(page_num))
                self.rest_page = np.random.randint(self.rest_min_page, self.rest_max_page)
                try:
                    for i in range(page_num):
                        if i % self.rest_page == 0 and i != 0:
                            print('[REST] rest {}s for cheating....'.format(self.rest_time))
                            time.sleep(self.rest_time)
                        fans_url_child = 'https://weibo.cn/{}/fans?page={}'.format(self.scrap_id, i)
                        print('requesting fans url: {}'.format(fans_url))
                        html_child = requests.get(
                            fans_url_child, cookies=self.cookie, headers=self.headers).content
                        selector_child = etree.HTML(html_child)
                        fans_ids_content = selector_child.xpath("//div[@class='c']/table//a[1]/@href")
                        ids = [i.split('/')[-1] for i in fans_ids_content]
                        ids = list(set(ids))
                        for d in ids:
                            print('appending fans id {}'.format(d))
                            fans_ids.append(d)
                except Exception as e:
                    print('Raise Exception in inner _get_fans_ids, error:', e)
                    dump_fans_list = list(set(fans_ids))
                    print(dump_fans_list)
                    with open(self.weibo_fans_save_file, 'w') as f:
                        f.write('\n'.join(dump_fans_list))
                    print('fans ids not fully added, but this is enough, saved into {}'.format(
                        self.weibo_fans_save_file))

                dump_fans_list = list(set(fans_ids))
                print(dump_fans_list)
                with open(self.weibo_fans_save_file, 'w') as f:
                    f.write('\n'.join(dump_fans_list))
                with open(self.big_v_ids_file, 'a') as f:
                    f.write(self.scrap_id + '\n')
                print('successfully saved fans id file into {}'.format(self.weibo_fans_save_file))

            except Exception as e:
                print('Raise Exception in outer _get_fans_ids, error:', e)


    def _get_weibo_content(self):
        print('\n' + '-' * 30)
        print('getting weibo content...')
        selector = etree.HTML(self.html)
        try:
            if not selector.xpath('//input[@name="mp"]'):
                page_num = 1
            else:
                page_num = int(selector.xpath('//input[@name="mp"]')[0].attrib['value'])
            pattern = r"\d+\.?\d*"
            print('all weibo page {}'.format(page_num))

            start_page = 0
            if os.path.exists(self.weibo_content_save_file):
                print('load previous weibo_content file from {}'.format(self.weibo_content_save_file))
                obj = pickle.load(open(self.weibo_content_save_file, 'rb'))
                if self.scrap_id in obj.keys():
                    self.weibo_content = obj[self.scrap_id]['weibo_content']
                    start_page = obj[self.scrap_id]['last_scrap_page']
            if start_page >= page_num:
                print('\nAll weibo contents of {} have been scrapped before\n'.format(self.user_name))
                return 

            self.rest_page = np.random.randint(self.rest_min_page, self.rest_max_page)
            # traverse all weibo, and we will got weibo detail urls
            for page in range(start_page + 1, page_num + 1): 
                try:
                    url2 = 'http://weibo.cn/%s?filter=%s&page=%s' % (self.scrap_id, self.filter, page)
                    html2 = requests.get(url2, cookies=self.cookie, headers=self.headers).content
                    selector2 = etree.HTML(html2)
                    content = selector2.xpath("//div[@class='c']")
                    print('\n---- current solving page {} of {}'.format(page, page_num))

                    if page % self.rest_page == 0:
                        print('[REST] rest for %ds to cheat weibo site, avoid being banned.'%self.rest_time)
                        time.sleep(self.rest_time)

                    if len(content) > 3:
                        for i in range(0, len(content) - 2):
                            detail = content[i].xpath("@id")[0]
                            self.weibo_detail_urls.append('http://weibo.cn/comment/{}?uid={}&rl=0'.
                                                          format(detail.split('_')[-1], self.scrap_id))

                            self.weibo_scraped += 1
                            str_t = content[i].xpath("div/span[@class='ctt']")
                            weibos = str_t[0].xpath('string(.)')
                            self.weibo_content.append(weibos)
                            print(weibos)

                            str_zan = content[i].xpath("div/a/text()")[-4]
                            guid = re.findall(pattern, str_zan, re.M)
                            num_zan = int(guid[0])
                            self.num_zan.append(num_zan)

                            forwarding = content[i].xpath("div/a/text()")[-3]
                            guid = re.findall(pattern, forwarding, re.M)
                            num_forwarding = int(guid[0])
                            self.num_forwarding.append(num_forwarding)

                            comment = content[i].xpath("div/a/text()")[-2]
                            guid = re.findall(pattern, comment, re.M)
                            num_comment = int(guid[0])
                            self.num_comment.append(num_comment)
                except etree.XMLSyntaxError as e:
                    print('\n\netree.XMLSyntaxError: ', e)
                    print('This page has no contents and is passed: ', e)

                except Exception as e:
                    print('Raise Exception in _get_weibo_content, error:', e)
                    print('\n' * 2)
                    print('=' * 20)
                    print('weibo user {} content scrap error occured {}.'.format(self.user_name, e))
                    print('all weibo {}, all like {}, all comments {}'.format(
                        len(self.weibo_content), np.sum(self.num_zan), np.sum(self.num_comment)))
                    print('try saving weibo content for now...')
                    self._save_content(page - 1)

            print('\n' * 2)
            print('=' * 20)
            print('all weibo {}, all like {}, all comments {}'.format(
                len(self.weibo_content), np.sum(self.num_zan), np.sum(self.num_comment)))
            print('try saving weibo content for now...')
            self._save_content(page)
            del self.weibo_content

            if self.filter == 0:
                print('共' + str(self.weibo_scraped) + '条微博')
            else:
                print('共' + str(self.weibo_num) + '条微博，其中' + str(self.weibo_scraped) + '条为原创微博')
        except IndexError as e:
            print('get weibo info done, current user {} has no weibo yet.'.format(self.scrap_id))
        except KeyboardInterrupt:
            print('\nManually interrupted... try save wb_content for now...')
            self._save_content(page - 1)
            print('Program exit!\n')
            exit()


    def _save_content(self, page):
        dump_obj = dict()
        if os.path.exists(self.weibo_content_save_file):
            with open(self.weibo_content_save_file, 'rb') as f:
                dump_obj = pickle.load(f)
            dump_obj[self.scrap_id] = {
                'weibo_content': self.weibo_content,
                'last_scrap_page': page
            }
            with open(self.weibo_content_save_file, 'wb') as f:
                pickle.dump(dump_obj, f)

        dump_obj[self.scrap_id] = {
            'weibo_content': self.weibo_content,
            'last_scrap_page': page
        }
        with open(self.weibo_content_save_file, 'wb') as f:
            pickle.dump(dump_obj, f)
        print('\nUser name: {} \t ID: {} '.format(self.user_name, self.scrap_id)) 
        print('[CHEER] weibo content saved into {}, finished this part successfully.\n'.format(
            self.weibo_content_save_file, page))


    def _get_weibo_content_and_comment(self):
        """
        all weibo will be saved into weibo_content_and_comment.pkl
        in format:
        {
            scrap_id: {
                'weibo_detail_urls': [....],
                'last_scrap_index': 5,
                'content_and_comment': [
                {'content': '...', 'comment': ['..', '...', '...', '...',], 'last_idx':num0},
                {'content': '...', 'comment': ['..', '...', '...', '...',], 'last_idx':num1},
                {'content': '...', 'comment': ['..', '...', '...', '...',], 'last_idx':num2}
                ]
            }
        }
        :return:
        """
        print('\n' + '-' * 30)
        print('getting content and comment...')
        weibo_detail_urls = self.weibo_detail_urls
        start_scrap_index = 0
        content_and_comment = []
        if os.path.exists(self.weibo_content_save_file):
            print('load previous weibo_content file from {}'.format(self.weibo_content_save_file))
            obj = pickle.load(open(self.weibo_content_save_file, 'rb'))
            if self.scrap_id not in obj.keys():
                print('\nID {} is not in self.weibo_content.keys()\n'.format(self.scrap_id))
                return False
            self.weibo_content = obj[self.scrap_id]['weibo_content']
                

        if os.path.exists(self.weibo_content_and_comment_save_file):
            #with open(self.weibo_content_and_comment_save_file, 'rb') as f:
            print('\nload previous weibo_content_and_comment file from {}'.format(
                self.weibo_content_and_comment_save_file))
            obj = pickle.load(open(self.weibo_content_and_comment_save_file, 'rb'))
            if self.scrap_id in obj.keys():
                obj = obj[self.scrap_id]
                weibo_detail_urls = obj['weibo_detail_urls']
                start_scrap_index = obj['last_scrap_index']
                content_and_comment = obj['content_and_comment']

        end_scrap_index = len(weibo_detail_urls)
        self.no_comment_weibo = 0
        try:
            for i in range(start_scrap_index + 1, end_scrap_index):
                if self.no_comment_weibo > self.raise_error_page:
                    raise CookiesOutdated()
                url = weibo_detail_urls[i]
                one_content_and_comment = dict()

                print('\nsolving weibo detail from {}'.format(url))
                print('\n{} No.{} weibo of total {}'.format(self.user_name, i, end_scrap_index))
                print('Weibo content: {}'.format(self.weibo_content[i]))
                print('Comments: \n\n')
                html_detail = requests.get(url, cookies=self.cookie, headers=self.headers).content
                selector_detail = etree.HTML(html_detail)
                if not selector_detail.xpath('//*[@id="pagelist"]/form/div/input[1]/@value'):
                    self.no_comment_weibo += 1
                    print('\nself.no_comment_weibo: %d\n'%self.no_comment_weibo)
                    continue
                all_comment_pages = selector_detail.xpath('//*[@id="pagelist"]/form/div/input[1]/@value')[0]
                # after get all comment pages, initialize one weibo content and its comment list
                one_content_and_comment['content'] = self.weibo_content[i]
                one_content_and_comment['comment'] = []
                start_idx = 0
                end_idx = int(all_comment_pages) - 2
                if i == start_scrap_index + 1 and content_and_comment:
                    print('+'*30)
                    print('\nTrying to recover from the last comment of last content...\n')
                    one_cac = content_and_comment[-1]
                    if 'last_idx' in one_cac.keys():
                        if one_cac['last_idx'] + 1 < end_idx:
                            one_content_and_comment['comment'] = one_cac['comment']
                            start_idx = one_cac['last_idx'] + 1
                            print('last_idx: {}\n'.format(one_cac['last_idx']))

                # start scrapping each page of comments
                start_time = time.time()
                self.rest_page = np.random.randint(self.rest_min_page, self.rest_max_page)
                print('\n\nself.rest_page: {}\n\n'.format(self.rest_page))
                no_content_pages = 0
                for page in range(start_idx, end_idx):
                    if no_content_pages > self.raise_error_page:
                        # record the error page
                        if i == self.error_page:
                            print('\n----- skip page %d -----\n '%i)
                            break
                        else:
                            self.error_page = i 
                            raise AccountBanned()
                    print('\n---- current solving page {} of {}'.format(page, end_idx - 1))
                    if (page + 1) % self.rest_page == 0:
                        self.rest_time = np.random.randint(self.rest_min_time, self.rest_max_time)
                        print('[ATTEMPTING] rest for %ds to cheat weibo site, avoid being banned.'%self.rest_time)
                        time.sleep(self.rest_time)

                    # we crawl from page 2, cause front pages have some noise
                    detail_comment_url = url + '&page=' + str(page + 2)
                    try:
                        # from every detail comment url we will got all comment
                        html_detail_page = requests.get(detail_comment_url, cookies=self.cookie).content
                        selector_comment = etree.HTML(html_detail_page)

                        comment_div_element = selector_comment.xpath('//div[starts-with(@id, "C_")]')
                        if not comment_div_element:
                            no_content_pages += 1
                            print('\nself.no_content_pages: %d\n'%no_content_pages)

                        for child in comment_div_element:
                            single_comment_user_name = child.xpath('a[1]/text()')[0]
                            if child.xpath('span[1][count(*)=0]'):
                                single_comment_content = child.xpath('span[1][count(*)=0]/text()')[0]
                            else:
                                span_element = child.xpath('span[1]')[0]
                                at_user_name = span_element.xpath('a/text()')[0]
                                at_user_name = '$' + at_user_name.split('@')[-1] + '$'
                                try :
                                    single_comment_content = span_element.xpath('text()')[1]
                                except Exception as e:
                                    #print('\nThis weibo reply has not comment.\n')
                                    continue

                            full_single_comment = '<' + single_comment_user_name + '>' + ': ' + single_comment_content
                            print(full_single_comment)
                            one_content_and_comment['comment'].append(full_single_comment)
                            one_content_and_comment['last_idx'] = page
                    except etree.XMLSyntaxError as e:
                        no_content_pages += 1
                        print('\n\nThis page has no contents and is passed: ', e)
                        print('Total no_content_pages: {}'.format(no_content_pages))
                    except Exception as e:
                        print('Raise Exception in _get_weibo_content_and_comment, error:', e)
                        print('\n' * 2)
                        print('=' * 20)
                        print('weibo user {} content_and_comment scrap error occured {}.'.format(self.user_name, e))
                        self._save_content_and_comment(i-1, one_content_and_comment, weibo_detail_urls)
                        print("\n\nComments are successfully save:\n User name: {}\n weibo content: {}\n\n".format(
                            self.user_name, one_content_and_comment['content']))

                # save one_content_and_comment
                end_time = time.time()
                self._save_content_and_comment(i, one_content_and_comment, weibo_detail_urls)
                print('*'*30)
                print("\n\nComments are successfully save:\n User name: {}\n weibo content: {}".format(
                    self.user_name, one_content_and_comment['content']))
                print('-----Total time cost of scrapping this weibo: %ds -----\n\n'%(end_time-start_time))
        except AccountBanned as e:
            print('Raise Exception in _get_weibo_content_and_comment, error:', e.msg)
            self._save_content_and_comment(i-1, one_content_and_comment, weibo_detail_urls)
            raise AccountBanned()
        except CookiesOutdated as e:
            raise CookiesOutdated()
        except KeyboardInterrupt:
            print('\nManually interrupted.. try save wb_content_and_comment for now...')
            self._save_content_and_comment(i-1, one_content_and_comment, weibo_detail_urls)
            print('Program exit!\n')
            exit()

        print('\n'*2)
        print('='*20)
        print('user {}, all weibo content and comment finished.'.format(self.user_name))
        print('[CHEER] weibo content and comment saved into {} successfully.'.format(
                self.weibo_content_and_comment_save_file))


    def _save_content_and_comment(self, i, one_content_and_comment, weibo_detail_urls):
        dump_dict = dict()
        if os.path.exists(self.weibo_content_and_comment_save_file):
            with open(self.weibo_content_and_comment_save_file, 'rb') as f:
                obj = pickle.load(f)
                dump_dict = obj
                if self.scrap_id in dump_dict.keys():
                    dump_dict[self.scrap_id]['last_scrap_index'] = i
                    dump_dict[self.scrap_id]['content_and_comment'].append(one_content_and_comment)
                else:
                    dump_dict[self.scrap_id] = {
                        'weibo_detail_urls': weibo_detail_urls,
                        'last_scrap_index': i,
                        'content_and_comment': [one_content_and_comment]
                    }
        else:
            dump_dict[self.scrap_id] = {
                'weibo_detail_urls': weibo_detail_urls,
                'last_scrap_index': i,
                'content_and_comment': [one_content_and_comment]
            }
        with open(self.weibo_content_and_comment_save_file, 'wb') as f:
            print('try saving weibo content and comment for now.')
            pickle.dump(dump_dict, f)   


    def switch_account(self, new_account):
        assert new_account.isinstance(str), 'account must be string'
        self.using_account = new_account

    @staticmethod
    def mark_as_scraped(scrap_id):
        """
        this will mark an id to be scraped, next time will jump this id directly
        :return:
        """
        scraped_ids = []
        if os.path.exists(SCRAPED_MARK):
            with open(SCRAPED_MARK) as f:
                scraped_ids = f.read().split('\n')
        scraped_ids.append(str(scrap_id))
        with open(SCRAPED_MARK, 'w') as f:
            f.write('\n'.join(scraped_ids))
        print('scrap id {} marked as scraped, next time will jump this id directly.'.format(scrap_id))
