# -*- coding: utf-8 -*-
'''
    rauth.session
    -------------

    Specially wrapped `request.Session` objects.
'''

from datetime import datetime
from hashlib import sha1, md5
from random import random
from time import time
from urllib import quote, urlencode
from urlparse import parse_qsl, urlsplit

from rauth.oauth import HmacSha1Signature
from rauth.utils import FORM_URLENCODED

from requests.sessions import Session

OAUTH1_DEFAULT_TIMEOUT = OAUTH2_DEFAULT_TIMEOUT = OFLY_DEFAULT_TIMEOUT = 300.0


class OAuth1Session(Session):
    '''
    A specialized `requests.sessions.Session` object, wrapping OAuth 1.0/a
    logic.

    This object is utilized by the `OAuth1Service` wrapper but can be used
    independently of that infrastructure. Essentially this is a loose wrapping
    around the standard Requests codepath. State may be tracked at this layer,
    especially if the instance is kept around and tracked via some unique
    identifier, e.g. access tokens. Things like request cookies will be
    preserved between requests and in fact all functionality provided by
    a Requests' `Session` object should be exposed here.

    If you were to use this object by itself you could do so by instantiating
    it like this::

        session = OAuth1Session('123',
                                '456',
                                access_token='321',
                                access_token_secret'654')

    You now have a session object which can be used to make requests exactly as
    you would with a normal Requests `Session` instance. This anticipates that
    the standard OAuth 1.0/a flow will be modeled outside of the scope of this
    class. In other words, if the fully qualified flow is useful to you then
    this object probably need not be used directly, instead consider using
    `OAuth1Service`.

    Once the session object is setup, you may start making requests::

        r = session.get('http://example/com/api/resource',
                        params={'format': 'json'})
        print r.json()

    :param consumer_key: Client consumer key.
    :param consumer_secret: Client consumer secret.
    :param access_token: Access token, defaults to None.
    :param access_token_secret: Access token secret, defaults to None.
    :param signature: A signature producing object, defaults to
        HmacSha1Signature.
    :param service: A back reference to the service wrapper, defaults to None.
    '''
    VERSION = '1.0'

    def __init__(self,
                 consumer_key,
                 consumer_secret,
                 access_token=None,
                 access_token_secret=None,
                 signature=None,
                 service=None):

        # consumer credentials
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

        # access token credentials
        self.access_token = access_token
        self.access_token_secret = access_token_secret

        # signing method
        if signature is None:
            self.signature = HmacSha1Signature()

        # a back reference to a service wrapper, if we're using one
        self.service = service

        super(OAuth1Session, self).__init__()

    def request(self,
                method,
                url,
                header_auth=False,
                realm=None,
                **req_kwargs):
        '''
        A loose wrapper around `requests.sessions.Session` which injects OAuth
        1.0/a params.

        :param method: A string representation of the HTTP method to be used.
        :param url: The resource to be requested.
        :param header_auth: Authenication via header, defaults to False.
        :param realm: The auth header realm, defaults to None.
        :param \*\*req_kwargs: Keyworded args to be passed down to Requests.
        '''

        req_kwargs.setdefault('timeout', OAUTH1_DEFAULT_TIMEOUT)

        self.oauth_params = {}

        # set the OAuth params on the oauth_params attribute
        self._set_oauth_params()

        # parse optional OAuth parameters
        for param in ('oauth_callback', 'oauth_verifier', 'oauth_version'):
            self._parse_optional_params(param, req_kwargs)

        # sign the request
        self.oauth_params['oauth_signature'] = self.signature.sign(self,
                                                                   method,
                                                                   url,
                                                                   req_kwargs)

        if header_auth:
            req_kwargs.setdefault('headers', {})
            req_kwargs['headers'].update({'Authorization':
                                           self._get_auth_header()})
        elif method.upper() in ('POST', 'PUT'):
            req_kwargs.setdefault('headers', {})
            req_kwargs['headers'].setdefault('Content-Type', FORM_URLENCODED)
            req_kwargs.setdefault('data', {})
            req_kwargs['data'].update(self.__dict__.pop('oauth_params'))
        else:
            req_kwargs.setdefault('params', {})
            req_kwargs['params'].update(self.__dict__.pop('oauth_params'))

        return super(OAuth1Session, self).request(method, url, **req_kwargs)

    def _parse_optional_params(self, oauth_param, req_kwargs):
        '''
        Parses and sets optional OAuth parameters on a request.

        :param oauth_param: The OAuth parameter to parse.
        :param req_kwargs: The keyworded arguments passed to the request
            method.
        '''
        params_is_string = type(req_kwargs.get('params')) == str
        data_is_string = type(req_kwargs.get('data')) == str

        params = req_kwargs.get('params', {})
        data = req_kwargs.get('data', {})

        # special handling if we're handed a string
        if params_is_string and params:
            params = dict(parse_qsl(params))

        # remove any oauth parameters and set them as attributes
        if oauth_param in params:
            self.oauth_params[oauth_param] = params.pop(oauth_param)
        if not data_is_string and oauth_param in data:
            self.oauth_params[oauth_param] = data.pop(oauth_param)

        # re-encode the params if they were a string, without any oauth
        if params_is_string:
            req_kwargs['params'] = urlencode(params)

    def _set_oauth_params(self):
        '''Prepares OAuth params for signing.'''
        self.oauth_params['oauth_consumer_key'] = self.consumer_key
        self.oauth_params['oauth_nonce'] = sha1(str(random())).hexdigest()
        self.oauth_params['oauth_signature_method'] = self.signature.NAME
        self.oauth_params['oauth_timestamp'] = int(time())

        if self.access_token is not None:
            self.oauth_params['oauth_token'] = self.access_token

        self.oauth_params['oauth_version'] = self.VERSION

    def _get_auth_header(self, realm=None):
        '''Constructs and returns an authentication header.'''
        oauth_params = self.__dict__.pop('oauth_params')
        auth_header = 'OAuth realm="{realm}"'.format(realm=realm)
        params = ''
        for k, v in oauth_params.items():
            params += ',{key}="{value}"'.format(key=k, value=quote(str(v)))
        auth_header += params
        return auth_header


class OAuth2Session(Session):
    '''
    A specialized `requests.sessions.Session` object, wrapping OAuth 2.0
    logic.

    This object is utilized by the `OAuth2Service` wrapper but can be used
    independently of that infrastructure. Essentially this is a loose wrapping
    around the standard Requests codepath. State may be tracked at this layer,
    especially if the instance is kept around and tracked via some unique
    identifier, e.g. access token. Things like request cookies will be
    preserved between requests and in fact all functionality provided by
    a Requests' `Session` object should be exposed here.

    If you were to use this object by itself you could do so by instantiating
    it like this::

        session = OAuth2Session('123', '456', access_token='321')

    You now have a session object which can be used to make requests exactly as
    you would with a normal Requests `Session` instance. This anticipates that
    the standard OAuth 2.0 flow will be modeled outside of the scope of this
    class. In other words, if the fully qualified flow is useful to you then
    this object probably need not be used directly, instead consider using
    `OAuth2Service`.

    Once the session object is setup, you may start making requests::

        r = session.get('https://example/com/api/resource',
                        params={'format': 'json'})
        print r.json()

    :param client_id: Client id.
    :param consumer_secret: Client secret.
    :param access_token: Access token, defaults to None.
    :param signature: A signature producing object, defaults to
        HmacSha1Signature.
    :param service: A back reference to the service wrapper, defaults to None.
    '''
    def __init__(self,
                 client_id,
                 client_secret,
                 access_token=None,
                 service=None):
        self.client_id = client_id
        self.client_secret = client_secret

        self.access_token = access_token

        self.service = service

        super(OAuth2Session, self).__init__()

    def request(self, method, url, **req_kwargs):
        '''
        A loose wrapper around `requests.sessions.Session` which injects OAuth
        2.0 params.

        :param method: A string representation of the HTTP method to be used.
        :param url: The resource to be requested.
        :param \*\*req_kwargs: Keyworded args to be passed down to Requests.
        '''
        req_kwargs.setdefault('params', {}).update({'access_token':
                                                    self.access_token})
        req_kwargs.setdefault('timeout', OAUTH2_DEFAULT_TIMEOUT)

        return super(OAuth2Session, self).request(method, url, **req_kwargs)


class OflySession(Session):
    '''
    A specialized `requests.sessions.Session` object, wrapping OAuth 2.0
    logic.

    This object is utilized by the `OAuth2Service` wrapper but can be used
    independently of that infrastructure. Essentially this is a loose wrapping
    around the standard Requests codepath. State may be tracked at this layer,
    especially if the instance is kept around and tracked via some unique
    identifier, e.g. access token. Things like request cookies will be
    preserved between requests and in fact all functionality provided by
    a Requests' `Session` object should be exposed here.

    If you were to use this object by itself you could do so by instantiating
    it like this::

        session = OAuth2Session('123', '456', access_token='321')

    You now have a session object which can be used to make requests exactly as
    you would with a normal Requests `Session` instance. This anticipates that
    the standard OAuth 2.0 flow will be modeled outside of the scope of this
    class. In other words, if the fully qualified flow is useful to you then
    this object probably need not be used directly, instead consider using
    `OAuth2Service`.

    Once the session object is setup, you may start making requests::

        r = session.get('https://example/com/api/resource',
                        params={'format': 'json'})
        print r.json()

    :param app_id: The oFlyAppId, i.e. "application ID".
    :param app_secret: The oFlyAppSecret, i.e. "shared secret".
    :param service: A back reference to the service wrapper, defaults to None.
    '''
    def __init__(self,
                 app_id,
                 app_secret,
                 service=None):
        self.app_id = app_id
        self.app_secret = app_secret

        self.service = service

        super(OflySession, self).__init__()

    def request(self, method, url, header_auth=False, **req_kwargs):
        '''
        A loose wrapper around `requests.sessions.Session` which injects Ofly
        params.

        :param method: A string representation of the HTTP method to be used.
        :param url: The resource to be requested.
        :param header_auth: Authenication via header, defaults to False.
        :param \*\*req_kwargs: Keyworded args to be passed down to Requests.
        '''
        req_kwargs.setdefault('params', {})
        req_kwargs.setdefault('headers', {})
        req_kwargs.setdefault('timeout', OFLY_DEFAULT_TIMEOUT)

        params, headers = OflySession.sign(url,
                                           self.app_id,
                                           self.app_secret,
                                           req_kwargs['params'])

        req_kwargs['params'].update(params)

        if header_auth:
            req_kwargs['headers'].update(headers)

        return super(OflySession, self).request(method, url, **req_kwargs)

    @staticmethod
    def sign(url, app_id, app_secret, hash_meth='sha1', **params):
        '''
        A signature method which generates the necessary Ofly parameters.

        :param app_id: The oFlyAppId, i.e. "application ID".
        :param app_secret: The oFlyAppSecret, i.e. "shared secret".
        :param hash_meth: The hash method to use for signing, defaults to
            "sha1".
        :param \*\*params: Additional parameters.
        '''
        if hash_meth == 'sha1':
            hash_meth = sha1
        elif hash_meth == 'md5':
            hash_meth = md5
        else:
            raise TypeError('hash_meth must be one of "sha1", "md5"')

        def param_sorting(params):
            def sorting_gen():
                for k in sorted(params.keys()):
                    yield '='.join((k, params[k]))
            return '&'.join(sorting_gen())

        now = datetime.utcnow()
        milliseconds = now.microsecond / 1000

        time_format = '%Y-%m-%dT%H:%M:%S.{0}Z'.format(milliseconds)
        ofly_params = {'oflyAppId': app_id,
                       'oflyHashMeth': hash_meth.upper(),
                       'oflyTimestamp': now.strftime(time_format)}

        url_path = urlsplit(url).path

        signature_base_string = app_secret + url_path + '?'

        # only append params if there are any, to avoid a leading ampersand
        sorted_params = param_sorting(params)
        if len(sorted_params):
            signature_base_string += sorted_params + '&'

        signature_base_string += param_sorting(ofly_params)

        params['oflyApiSig'] = hash_meth(signature_base_string).hexdigest()

        # return the raw ofly_params for use in the header
        return param_sorting(params), ofly_params