#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


import json
from datetime import datetime

import endpoints

from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import StringMessage
from models import BooleanMessage
from models import TeeShirtSize
from models import (Profile, ProfileMiniForm, ProfileForm)
from models import (Conference, ConferenceForm, ConferenceForms,
                    ConferenceQueryForm, ConferenceQueryForms)
from models import (Session, SessionForm, SessionForms)
from models import (Speaker, SpeakerForm)

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')

MEMCACHE_FSPEAKER_KEY = "RECENT_FEATURED_SPEAKER"
FSPEAKER_TPL = ('{0} featured in the following sessions: {1}')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

SESS_DEFAULTS = {
    "highlights": ['Default', 'Highlights'],
    "typeOfSession": "lecture",
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS = {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

WISHLIST_POST = endpoints.ResourceContainer(
    sessionKey=messages.StringField(1),
)

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    typeOfSession=messages.StringField(2),
)

SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),

)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
               allowed_client_ids=[WEB_CLIENT_ID,
                                   API_EXPLORER_CLIENT_ID,
                                   ANDROID_CLIENT_ID,
                                   IOS_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    # this maybe qualifies as transactional.
    # what needs to be done to work, is to put allocate ids outside of the transaction,
    # and ndb.put_multi([prof, conf]) in a transaction
    def _createConferenceObject(self, request):
        """Create or update Conference object.

        If profile doesn't exist create it also
        return:
            ConferenceForm/request.
        """
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get/create profile
        prof = self._getProfileFromUser()
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID

        p_key = prof.key

        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()

        taskqueue.add(params={'email': user.email(),
                      'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email')
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException('No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(
                   conf,
                   getattr(prof, 'displayName')) for conf in confs]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"],
                                                   filtr["operator"],
                                                   filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])
                       for conf in conferences]
        )


# - - - Conference Sessions - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _makeTransaction(self, session, speaker):
        """Save the session and featured speaker in a transaction"""

        Session(**session).put()
        speaker.featuredSessions.append(session['key'].urlsafe())
        speaker.put()

        return (session, speaker)

    def _createSessionObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        wsck = request.websafeConferenceKey

        del data['websafeKey']

        conf = ndb.Key(urlsafe=wsck).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')
        # Create the Session Object from Input
        # add default values for those missing (both data model & outbound Message)
        for df in SESS_DEFAULTS:
            if data[df] in (None, []):
                data[df] = SESS_DEFAULTS[df]
                setattr(request, df, SESS_DEFAULTS[df])

        # convert dates from strings to Date and Time objects respectively
        if data['date']:
            data['date'] = datetime.strptime(data['date'][:10], "%Y-%m-%d").date()
        if data['startTime']:
            data['startTime'] = datetime.strptime(data['startTime'][:5], "%H:%M").time()

        c_key = conf.key
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # get the speaker Object

        del data['websafeConferenceKey']

        # creation of Session & return (modified) SessionForm

        return data

    # Helper to Copy relevant fields from Session to SessionForm."""
    def _copySessionToForm(self, sess):
        """Copy relevant fields from Conference to ConferenceForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # convert Date to date string; just copy others
                if field.name == 'date':
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                elif field.name == 'startTime':
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, sess.key.urlsafe())
        # Checks that all required fields are initialized.
        sf.check_initialized()
        return sf

    # Given a conference, return all sessions
    @endpoints.method(CONF_GET_REQUEST, SessionForms,
                      path='conference/sessions/{websafeConferenceKey}',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Return all sessions by conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck)
        if not conf.kind() == "Conference":
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        sessions = Session.query(ancestor=conf)
        sessions = sessions.order(Session.date, Session.startTime, Session.name)

        # return individual SessionForm object per Session
        return SessionForms(
                items=[self._copySessionToForm(sess)
                       for sess in sessions])

    # Given a conference, return all sessions of a specified type
    @endpoints.method(SESS_GET_REQUEST, SessionForms,
                      path='conference/sessions/{websafeConferenceKey}/{typeOfSession}',
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Query sessions for a specified type (by websafeConferenceKey)."""
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck)
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        sessions = Session.query(ancestor=conf)
        sessions = sessions.filter(Session.typeOfSession == request.typeOfSession)
        sessions = sessions.order(Session.date, Session.startTime, Session.name)

        return SessionForms(
                items=[self._copySessionToForm(sess)
                       for sess in sessions]
        )

    # Create Session Endpoint
    @endpoints.method(SESS_POST_REQUEST, SessionForm,
                      path='conference/sessions/{websafeConferenceKey}',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new session in conference (by websafeConferenceKey)."""

        # to make transaction work I had to allocate ids outside of the transction
        session = self._createSessionObject(request)
        speaker = self._getOrCreateSpeaker(request.speaker)
        # and update datastore inside the transaction
        session, speaker = self._makeTransaction(session, speaker)

        if len(speaker.featuredSessions) > 1:
            taskqueue.add(params={'speaker': speaker.fullName},
                          url='/tasks/featured_speaker')

        return self._copySessionToForm(request)

    # Return all sessions which are not workshop and are before 7 AM.
    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='sessions/query',
                      http_method='GET', name='getSessionsProblematicQuery')
    def getSessionsProblematicQuery(self, request):
        """Query sessions with two inequallite filters"""

        q = Session.query()

        # get time limits
        time_up = datetime.strptime('19:00', '%H:%M').time()
        time_down = datetime.strptime('00:00', '%H:%M').time()

        # ndb filter one inequality ( typeOfSession)
        q = q.filter(Session.typeOfSession != "workshop")
        # This has to be first
        q = q.order(Session.typeOfSession)
        q = q.order(Session.date, Session.startTime, Session.name)

        retSess = SessionForms(
                    items=[self._copySessionToForm(sess)
                           for sess in q
                           if sess.startTime < time_up]  # filter out sessions by time limits
        )

        return retSess


# - - - Speaker  - - - - - - - - - - - - - - - - - - -

    def _getOrCreateSpeaker(self, speakers_name):
        """Get Speaker from datastore

        If the speaker doesn't exist create an entry
        return:
            Speaker
        """
        q = Speaker.query(Speaker.fullName == speakers_name)

        sp = q.get()
        # create new Profile if not there
        if not sp:
            sp = Speaker(
                fullName=speakers_name,
            )
            sp.put()

        return sp  # return Speaker

    def _copySpeakerToForm(speaker):
        """Copy relevant fields from Session to SessionForm."""
        sf = SpeakerForm()
        for field in sf.all_fields():
            if hasattr(speaker, field.name):
                setattr(sf, field.name, getattr(speaker, field.name))
        sf.check_initialized()
        return sf

    @staticmethod
    def _cacheFeaturedSpeaker(speakers_name):
        """Create Featured Speaker & assign to memcache; used by
        getFeaturedSpeakers().
        """
        speaker = Speaker.query(Speaker.fullName == speakers_name).get(use_cache=False, use_memcache=False)

        if speaker:
            s_keys = [ndb.Key(urlsafe=wssk) for wssk in speaker.featuredSessions]
            sessions = ndb.get_multi(s_keys)
            print len(s_keys)
            print len(sessions)

            sessions_names = ', '.join([sess.name for sess in sessions])
            # create a message for display
            fspeaker = FSPEAKER_TPL.format(speaker.fullName, sessions_names)
            memcache.set(MEMCACHE_FSPEAKER_KEY, fspeaker)

        else:
            # If it gets called with no args,
            # delete the memcache featured speaker entry
            fspeaker = ""
            memcache.delete(MEMCACHE_FSPEAKER_KEY)

        return fspeaker

    # get featured speaker from memcache.
    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='featured-speaker',
                      http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Get most recent speaker featured in more than one sessions"""
        return StringMessage(data=memcache.get(MEMCACHE_FSPEAKER_KEY) or "")

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile  # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        # if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        # else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")


# - - - User Wishlist - - - - - - - - - - - - - - - - - - - -

    def _appendToWishlist(self, request, flag=True):
        """Add or delete Session in user's Wishlist ."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if session exists given sessionKey
        # get session; check that it exists
        s_key = request.sessionKey
        key = ndb.Key(urlsafe=s_key)

        if key.kind() != "Session":
            raise endpoints.NotFoundException(
                'No session found with key: %s' % s_key)

        session = key.get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % s_key)

        # add
        if flag:
            # check if user already wishlisted this session otherwise add
            if s_key in prof.sessionWishlist:
                raise ConflictException(
                    "You have already added this session to the wishlist")

            # register user, take away one seat
            prof.sessionWishlist.append(s_key)
            retval = True

        # delete
        else:
            # check if user already registered
            if s_key in prof.sessionWishlist:

                # unregister user, add back one seat
                prof.sessionWishlist.remove(s_key)
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        return BooleanMessage(data=retval)

    @endpoints.method(WISHLIST_POST, BooleanMessage,
                      path='wishlist/{sessionKey}',
                      http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add session to user's widhlist."""
        return self._appendToWishlist(request)

    @endpoints.method(WISHLIST_POST, BooleanMessage,
                      path='wishlist/{sessionKey}',
                      http_method='DELETE', name='deleteSessionInWishlist')
    def deleteSessionInWishlist(self, request):
        """Add session to user's widhlist."""
        return self._appendToWishlist(request, flag=False)

    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='wishlist',
                      http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        sess_keys = [ndb.Key(urlsafe=s_key) for s_key in prof.sessionWishlist]
        sessions = ndb.get_multi(sess_keys)

        # return set of SessionForm
        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions])


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])
                                      for conf in conferences])

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='filterPlayground',
                      http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city == "London")
        q = q.filter(Conference.topics == "Medical Innovations")
        q = q.filter(Conference.month == 6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )


api = endpoints.api_server([ConferenceApi])  # register API
