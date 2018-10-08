#!/usr/bin/env python
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2017
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
import itertools
import json
import os
import time

import _pytest.config
import certifi
import pytest
import telegram.vendor.ptb_urllib3.urllib3 as urllib3
from future.backports.urllib.parse import quote_plus

import tests

terminal = None


def partition(items, predicate=bool):
    a, b = itertools.tee((predicate(item), item) for item in items)
    return ((item for pred, item in a if not pred),
            (item for pred, item in b if pred))


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    global terminal
    if terminal is None:
        terminal = _pytest.config.create_terminal_writer(config)

    def predicate(item):
        try:
            if list(item.iter_markers(name='conflicting')):
                return True
        except KeyError:
            pass

    non_conflicting, conflicting = partition(items, predicate)

    conflicting = list(conflicting)
    if conflicting:
        parent = next(candidate for candidate in conflicting[0].listchain()
                      if hasattr(candidate, 'module') and candidate.module == tests)

        parent = parent.Module(os.path.realpath(__file__), parent=parent)
        wait = parent.Function('test_travis_wait_for_non_conflicting_bot',
                               parent=parent)
        conflicting.insert(0, wait)

    session.items = list(non_conflicting) + conflicting


def test_travis_wait_for_non_conflicting_bot(capsys):
    with capsys.disabled():
        terminal.write('\nChecking for other running jobs\n')
        http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

        while 1:
            slug = os.getenv('TRAVIS_REPO_SLUG')
            if not slug:
                return
            slug = quote_plus(slug)

            my_job_id = int(os.getenv('TRAVIS_JOB_ID', 0))
            if my_job_id == 0:
                return

            url = 'https://api.travis-ci.org/repo/{}/builds'.format(slug)
            r = http.request(
                'GET',
                url,
                fields={
                    'include': 'build.jobs',
                    'state': 'started'
                },
                headers={
                    'Travis-API-Version': 3,
                    'User-Agent': 'python-telegram-bot build system'
                }
            )

            data = json.loads(r.data.decode('utf-8'))

            jobs = itertools.chain(*[build['jobs'] for build in data['builds']])
            jobs = [job for job in jobs if job['state'] == 'started']
            jobs.sort(key=lambda job: job['id'])

            if not jobs:
                return

            queue = ';'.join([str(job['id']) for job in jobs])
            terminal.write('\rMy id: {} | Queue: {}'.format(my_job_id, queue))

            if my_job_id == jobs[0]['id']:
                terminal.write('\nIt is my turn to continue, wooo :D\n')
                return

            time.sleep(5)
