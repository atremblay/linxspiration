#! /Users/alexis/anaconda/bin/python
# -*- coding: utf-8 -*-
# @Author: alexis
# @Date:   2015-06-22 17:53:03
# @Last Modified by:   alexis
# @Last Modified time: 2015-09-19 14:26:15

from bs4 import BeautifulSoup
import urllib.request as urllib
import json
import datetime
import os
import logging
import argparse
import asyncio
import aiohttp
import concurrent
from concurrent.futures import ThreadPoolExecutor
from functools import partial

base_url = 'http://linxspiration.com/tagged/'
tags = [
        'architecture',
        'cars',
        'gear',
        'interiors',
        'menswear',
        'landscape'
    ]


class ImageLog(object):
    """docstring for ImageLog"""
    def __init__(self):
        super(ImageLog, self).__init__()
        home_dir = os.path.expanduser('~')
        log_path = 'Pictures/linxspiration/linxspiration.log'
        self.path = os.path.join(home_dir, log_path)

        self.log = set()

        if os.path.exists(self.path) and os.path.isfile(self.path):
            with open(self.path, 'r') as log_file:
                j_log_file = json.load(log_file)
                self.log.update(j_log_file['images'])

    def add(self, image):
        self.log.add(image)

    def has(self, image):
        return image in self.log

    def save(self):
        now = datetime.datetime.now()
        log_file = open(self.path, 'w')
        log = {
            "images": list(self.log),
            "updated": now.strftime("%Y-%m-%d %H:%M")
            }

        json.dump(log, log_file, indent=4)
        log_file.close()


def args():
    parser = argparse.ArgumentParser(
        description='Script pour aller chercher'
        ' les images disponibles sur linxspiration')
    parser.add_argument(
        '-l', '--log', metavar='N', default='INFO',
        help='Niveau de logging')
    return parser.parse_args()


def create_dirs():
    for tag in tags:
        path = os.path.join(os.path.expanduser('~'), 'Pictures/linxspiration', tag)
        if os.path.exists(path):
            if os.path.isdir(path):
                continue
            else:
                os.mkdir(path)
        else:
            os.mkdir(path)


@asyncio.coroutine
def get_source(url):
    response = yield from aiohttp.request('GET', url)
    content = yield from response.read_and_close()
    return content


@asyncio.coroutine
def get_main_links(tag):
    logging.info("Getting main links for tag {}".format(tag))
    page = 1
    images_urls = []

    while page < 20:
        logging.debug("  Page %s", page)
        url = base_url + tag + '/page/' + str(page)
        logging.debug("  url: {}".format(url))

        sem = asyncio.Semaphore(10)
        with (yield from sem):
            source = yield from get_source(url)
        soup = BeautifulSoup(source)
        divs = soup.find_all('div', {'class': 'media'})

        for div in divs:
            try:
                a = div.find('a', {'target': '_blank'})
                # logging.debug(a)
                images_urls.append(a.attrs['href'])
            except AttributeError:
                continue
        page += 1

    logging.debug("Found {} main links for {}".format(len(images_urls), tag))
    return tag, images_urls


@asyncio.coroutine
def get_secondary_links(tag, links):
    logging.info("Getting secondary links for {}".format(tag))
    images_urls = []
    for link in links:
        sem = asyncio.Semaphore(10)
        with (yield from sem):
            source = yield from get_source(link)
        soup = BeautifulSoup(source)
        divs = soup.find_all('div', {'class': 'media'})

        for div in divs:
            try:
                img = div.find('img')
                # logging.debug(img)
                images_urls.append(img.attrs['src'])
            except AttributeError:
                logging.info(link)
                continue
    logging.info("Found {} secondary links".format(len(images_urls)))
    return tag, images_urls


def get_image(tag, link):
    path = link.split('/')
    image = path[-1]

    logging.info("Fetching {}::{}".format(tag, link))
    image_path = os.path.join(os.path.expanduser('~'), 'Pictures/linxspiration', tag, image)
    urllib.urlretrieve(link, image_path)

    return link


@asyncio.coroutine
def main():
    create_dirs()
    image_log = ImageLog()

    loop = asyncio.get_event_loop()

    executor = ThreadPoolExecutor(max_workers=5)
    futures = []

    for main_future in asyncio.as_completed(
            [get_main_links(tag) for tag in tags]):

        tag, main_links = yield from main_future

        for second_future in asyncio.as_completed(
                [get_secondary_links(tag, main_links)]):

            tag, second_links = yield from second_future
            logging.debug("({}, {})".format(tag, second_links))

            for second_link in second_links:
                if not image_log.has(second_link):
                    logging.debug("{} not in log".format(second_link))
                    future = executor.submit(
                        get_image, tag, second_link)
                    futures.append(future)

    for future in concurrent.futures.as_completed(futures):
        if future.exception() is not None:
            logging.info("Could not fetch ")
        else:
            logging.info("Fetched {}".format(future.result()))
            image_log.add(future.result())

    image_log.save()

if __name__ == '__main__':
    args = args()
    level = getattr(logging, args.log.upper(), None)
    if not isinstance(level, int):
        raise ValueError('Invalid log level: %s' % loglevel)

    logging.basicConfig(level=level, format='%(levelname)s:: %(message)s')
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
