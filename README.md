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

#### Session Class

**SessionKey**: The session belongs to a conference and as so it's key should have the conference as an ancestor.  
**Start time**: `ndb.TimeProperty()` it should always have an input in following the 24h notation. e.g: 17:00.  
**Duration**: `IntigerProperty`  Easier to order by duration or make calculations.  
**Speaker**: `ndb.KeyProperty(Speaker)`   
To manage the relationship between speakers and sessions this property holds the speaker's key.  

#### Speaker Class

**key** Auto generated by datastore  
**fullName** `StringProperty` Holds the Speaker's full name.  
**email** `StringProperty`  
**featuredSessions** For the sake of simplicity this property is not stored in the datasotre. It returns a query for the sessions the Speaker is featured.  

```python
@property
"""Returns a Session query object for sessions this Speaker is featured"""
def featuredSessions(self):
    return Session.query(Session.speaker == self.key)
```
So querying for Speaker sessions:
```python
sessions = speaker.featuredSessions.fetch()
```
This way is easier to update the session entity with a different speaker.  
The backend API also provides endpoints for Speaker fetching/creation and Session update. To assign a Speaker to a Session
 you have to provide a urlsafe string of the Speakers key as the `speaker` field for the `Session` entity.

See the GoogleCloudPlatform/python-docs-samples repo for great [modeling][7]  examples.

### Additional queries

- Users can follow conferences that they are interested in and are full.
When a spot empties the get notified by an email. This is implemented using a cron job every 6 hours to query datastore. A 2 helper properties has been added to the `Conference` class  
```python
followedBy = ndb.StringProperty(repeated=True)
hasFollowers = ndb.ComputedProperty(lambda self: len(self.followedBy) != 0)
```  
To follow, the conference must be full. When a Conf has an empty seat, a task then gets created by the cron to send emails to the followers and delete them from the list.

- Users can query for sessions in conferences they are registered for a given date or date range.


## Problematic Query

>Let’s say that you don't like workshops and you don't like sessions after 7 pm. How would you handle a query for all non-workshop sessions before 7 pm? What is the problem for implementing this query? What ways to solve it did you think of?

The way we normally would handle this query is to query for all sessions before 19:00 and are not workshops.  
The problem with app-engine though is that we can not have in the same query inequality filters for more than one properties.  
One solution in this problem would be to first query datastore for all sessions that are not workshops and after we get the results use python and filter out the sessions after 19:00.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
[7]: https://github.com/GoogleCloudPlatform/python-docs-samples/tree/master/appengine/ndb/modeling
