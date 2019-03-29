from __future__ import print_function

import os
import logging
from threading import Thread
from queue import Queue
from wsgiref.simple_server import make_server

from github import Github, GithubException
from kubernetes import client, config

from pyramid.config import Configurator
from pyramid.view import view_config, view_defaults
from pyramid.response import Response

USERNAME = os.environ.get('GIT_USERNAME', None)
PASSWORD = os.environ['GIT_PASSWORD']
ORGANIZATION = os.environ['GIT_ORGANIZATION']

EXTERNAL_HOST = os.environ['EXTERNAL_HOST']
CALLBACK_PATH = os.environ['CALLBACK_PATH']

NAMESPACE = os.environ['NAMESPACE']
PATH = os.environ['PATH']
STORAGE_SIZE = os.environ['STORAGE_SIZE']

LOGGING_LEVEL = os.environ.get('LOGGING_LEVEL', 'INFO')
INCLUSTER = bool(os.environ.get('INCLUSTER', False))

if INCLUSTER:
    config.load_incluster_config()
else:
    config.load_kube_config()

user_queue = Queue()

def create_pv(username, namespace, path, storage_size):
    name = 'gpfs-{!s}'.format(username)

    claim_name = 'claim-{!s}'.format(username)

    path = os.path.join(path, username)

    metadata = client.V1ObjectMeta(name=name, namespace=namespace)

    claim_ref = client.V1ObjectReference(namespace=namespace, name=claim_name)

    host_path = client.V1HostPathVolumeSource(path, 'DirectoryOrCreate')

    spec = client.V1PersistentVolumeSpec(
        access_modes=[
            'ReadWriteOnce',
        ], 
        capacity={
            'storage': storage_size,
        }, 
        claim_ref=claim_ref, 
        host_path=host_path, 
        storage_class_name='gpfs',
        persistent_volume_reclaim_policy='Retain',
        volume_mode='Filesystem')

    pv = client.V1PersistentVolume('v1', 'PersistentVolume', metadata, spec)

    return pv

def handle_k8s_provisions():
    logging.info('Handling provision requests')

    core = client.CoreV1Api()

    while True:
        login = user_queue.get()

        logging.info('Processing request for user %r', login)

        pv = create_pv(login, NAMESPACE, PATH, STORAGE_SIZE)

        try:
            core.create_persistent_volume(body=pv)
        except client.rest.ApiException as e:
            logging.debug('Failed to create with error %s', e)

            logging.info('Failed to create a PersistentVolume for %s', login)

            pass
        else:
            logging.info('Successfully created PersistentVolume for %s', login)

def create_github_webhook(org):
    config = {
        'url': '{!s}/{!s}'.format(EXTERNAL_HOST, CALLBACK_PATH),
        'content_type': 'json',
    }

    logging.info('Attempting to register webhook on %s with payload %s', org.id, config)

    try:
        org.create_hook('web', config, 'member', active=True)
    except GithubException as e:
        logging.info('Failed to register webhook status: %s reason: %s', e.status, e.data)

        pass
    else:
        logging.info('Successfully registered webhook')

def check_existing_users(org):
    logging.info('Checking existing users k8s PersistentVolumes')

    for user in org.get_members():
        logging.info('Queueing user %s', user.login)

        user_queue.put(user.login)

    logging.info('Queued all existing users')

@view_defaults(route_name=CALLBACK_PATH, renderer='json', request_method='POST')
class PayloadView(object):
    def __init__(self, request):
        self.request = request
        self.payload = self.request.json

    @view_config(header='X-Github-Event:member_added')
    def payload_member_added(self):
        login = self.payload['sender']['login']
        logging.info('Member %s added', login)

        user_queue.put(login)

        return {'status': 200}

    @view_config(header='X-Github-Event:ping')
    def payload_ping(self):
        logging.info('Pinged with id %s', self.payload['hook']['id'])
        return {'status': 200}

def main():
    logging.basicConfig(level=LOGGING_LEVEL)

    logging.info('Creating provisioner thread')

    user_thread = Thread(target=handle_k8s_provisions)

    user_thread.start()

    logging.info('Created provisioner thread %r', user_thread.ident)

    if USERNAME is None:
        g = Github(PASSWORD)

        logging.info('Logging into Github with a token')
    else:
        g = Github(USERNAME, PASSWORD)

        logging.info('Logging into Github with username/password')

    org = g.get_organization(ORGANIZATION)

    logging.info('Retrieved organization %r', org.id)

    check_existing_users(org)

    create_github_webhook(org)

    logging.info('Configuring webserver')

    config = Configurator()
    config.add_route(CALLBACK_PATH, '/{!s}'.format(CALLBACK_PATH))
    config.scan()

    logging.info('Creating wsgi app')

    app = config.make_wsgi_app()

    logging.info('Starting web server at 0.0.0.0:8000')

    server = make_server('0.0.0.0', 8000, app)
    server.serve_forever()