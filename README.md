## Scalable-py

Cloud-based API server to support a provided conference organization application that exists on the web as well as a native Android application. The API supports the following functionality found within the app: user authentication, user profiles, conference information and various manners in which to query the data

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.

## Design decisions

### Session and Speaker Implementation

The implementation is pretty straightforward.

**SessionKey**: The session belongs to a conference and as so it's key should have the conference as an ancestor.

**Start time**: This is an `ndb.TimeProperty()` it should always have an input in following the 24h notation. e.g: 17:00.

**Speaker**: As these could be made in a lot of ways I chose what I thought  simplest, just store the speakers fullname (required field). However there is a Speaker entity also.
When a user creates a session and assigns a speaker the application gets that Speaker entity from the datastore quering by `Speaker.fullName`, if there isn't any records that entity gets created before assigning the speaker to the session. The assignment happens in a transactional way immediately afterwards.
In the speaker entity there is a list of the sessions the speaker is featured (assigned).

### Additional queries

- Users can follow conferences that they are interested in and are full.
When a spot empties the get notified by an email (cron job, task queue).

- Users can query for sessions in conferences they are registered for a given date or date range.


## Problematic Query

>Let’s say that you don't like workshops and you don't like sessions after 7 pm. How would you handle a query for all non-workshop sessions before 7 pm? What is the problem for implementing this query? What ways to solve it did you think of?

The way we normally would handle this query is to query for all sessions before 19:00 and are not workshops.  
The problem with app-engine though is that we can not have in the same query inequality filters for more than one different properties.  
The solution in this problem would be to first query datastore for all sessions that are not workshops and after we get the results use python and filter out the sessions after 19:00.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
