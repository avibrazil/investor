import logging
import sqlalchemy
import pandas as pd


# TODO: Convert all queries to SQLAlchemy methods


class DataCache(object):
    """
    Implements a simple generic cache in a local SQLite database.

    Time series for market indexes, currency converters and even your portfolio kept on
    Google Sheets takes a lot of time to load because they are published as slow web APIs.

    To speed up initial data loading, all classes in the investor framework know how to
    work with a DataCache.

    A dataset that needs to be cached can have arbitrary columns and is usually the raw
    data as returned by the web API, before cleanup and processing.

    A dataset has a `kind` and `ID`. So for example, the YahooMarketIndex class has kind
    `YahooMarketIndex` and the `ID` might be `^IXIC` or `^GSPC` the name of the market
    index you put in your portfolio configuration.

    DataCache will organize tables in the database with names `DataCache__{kind}`. And
    then each table will have columns:

    - __DataCache_id: values for our YahooMarketIndex examples will be `^IXIC` or `^GSPC`
    - __DataCache_time: UTC time the cache was set
    - other arbitrary columns found in the data attribute of set() method

    DataCache will keep multiple versions of the dataset, differentiated by
    __DataCache_time and it will always use the last version (max(__DataCache_time)). The
    maximum number of versions kept are defined by the __init__()’s recycle attribute.
    Older versions of data will be automatically deleted.
    """

    idCol       = '__DataCache_id'
    timeCol     = '__DataCache_time'
    typeTable   = 'DataCache__{kind}'



    def __init__(self, url='sqlite:///cache.db', recycle=5):
        self.url=url
        self.db=None
        self.recycle=recycle

        # Setup logging
        self.getLogger()

        self.getDB()


    def __repr__(self):
        return 'DataCache(url={url},recycle={recycle})'.format(
            url=self.url,
            recycle=self.recycle
        )



#     def __del__(self):
#         if hasattr(self,'db') and self.db:
#             self.db.close()
#             self.db=None



    def __getstate__(self):
        o = self.__dict__
        o.update(
            dict(
                db = None,
                logger = None
            )
        )
        return o



    def getLogger(self):
        if hasattr(self,'logger')==False or self.logger is None:
            self.logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        return self.logger


    def getDB(self):
        sqlite_fake_multithreading=dict(
            poolclass         = sqlalchemy.pool.QueuePool,
            pool_size         = 1,
            max_overflow      = 0,

            # virtually wait forever until the used connection is freed
            pool_timeout      = 3600.0
        )

        if hasattr(self,'db')==False or self.db is None:
            self.getLogger().debug(f"Creating a DB engine on {self.url}")

            self.db=sqlalchemy.create_engine(
                url = self.url,
                **sqlite_fake_multithreading
            )

        return self.db



    def last(self, kind, id):
        """
        Return last time data was updated on cache for this kind and id
        """

        table=self.typeTable.format(kind=kind)

        q='''
            SELECT max({timeCol}) AS last
            FROM {typeTable}
            WHERE {idCol} = '{id}'
        '''

        self.getDB()

        query=q.format(
            typeTable     = table,
            idCol         = self.idCol,
            timeCol       = self.timeCol,
            id            = id
        )

        try:
            self.getLogger().debug(f'Trying cache as {query}')

            df=pd.read_sql(query,con=self.db)

            if df.shape[0]>0:
                self.logger.debug(f"Successful cache hit for kind={kind} and id={id}")
                df['last']=pd.to_datetime(df['last'])
                ret=df['last'][0]
                if ret.tzinfo is None or ret.tzinfo.utcoffset(ret) is None:
                    ret=ret=ret.tz_localize('UTC')
            else:
                self.getLogger().info(f"Cache empty for kind={kind} and id={id}")
                ret=None
        except Exception as e:
            self.getLogger().info(f"No cache for kind={kind} and id={id}")
            self.getLogger().info(e)
            ret=None


        return ret



    def get(self, kind, id, time=None):
        """
        kind leads to table DataCache_{kind}

        id is written to column __DataCache_id

        time makes it search on column __DataCache_time for entries with id recent up to time
        """

        table=self.typeTable.format(kind=kind)

        if time is None:
            pointInTime='''
            (
                SELECT DISTINCT {timeCol}
                FROM {typeTable}
                WHERE {idCol} = '{id}'
                ORDER BY {timeCol} DESC
                LIMIT 1
            )
            '''
        else:
            pointInTime='''
            (
                SELECT DISTINCT {timeCol}
                FROM {typeTable}
                WHERE
                    {idCol}    = '{id}' AND
                    {timeCol} <= '{time}'
                ORDER BY {timeCol} DESC
                LIMIT 1
            )
            '''

        pointInTime=pointInTime.format(
            timeCol      = self.timeCol,
            time         = time,
            idCol        = self.idCol,
            id           = id,
            typeTable    = table
        )

        query='''
            SELECT *
            FROM {typeTable}
            WHERE
                {idCol}   = '{id}' AND
                {timeCol} = {pointInTime}
        '''

        query=query.format(
            typeTable    = table,
            idCol        = self.idCol,
            timeCol      = self.timeCol,
            id           = id,
            pointInTime  = pointInTime
        )

        self.getDB()

        try:
            self.getLogger().debug(f'Trying cache as {query}')

            df=pd.read_sql(query,con=self.db)

            if df.shape[0]>0:
                self.getLogger().debug(f"Successful cache hit for kind={kind} and id={id}")
                ret=df.drop(columns=[self.timeCol,self.idCol])
            else:
                self.getLogger().info(f"Cache empty for kind={kind} and id={id}")
                ret=None
        except Exception as e:
            self.getLogger().info(f"No cache for kind={kind} and id={id}")
            self.getLogger().info(e)
            ret=None

        return ret



    def cleanOld(self, kind, id):
        # Next query is overcomplicated because couldn’t make work its simplest version:
        # cleanQuery='''
        #     DELETE
        #     FROM {typeTable}
        #     WHERE {idCol} = '{id}'
        #     AND {timeCol} <= coalesce(
        #         (
        #             SELECT DISTINCT {timeCol}
        #             FROM {typeTable}
        #             WHERE {idCol} = '{id}'
        #             ORDER BY {timeCol} DESC
        #             limit 1 offset {recycle}
        #         ),
        #         date(0)
        #     )
        # '''

        # This query also doesn’t work flawlessly probably because of dead lock
        # https://stackoverflow.com/a/52467973/367824
        # cleanQuery='''
        #     WITH oldest AS (
        #         SELECT DISTINCT {timeCol}
        #         FROM {typeTable}
        #         WHERE {idCol} = '{id}'
        #         ORDER BY {timeCol} DESC limit 1 offset {recycle}
        #     )
        #     DELETE FROM {typeTable}
        #     WHERE EXISTS (
        #         SELECT 1
        #         FROM oldest
        #         WHERE {typeTable}.{timeCol} <= oldest.{timeCol}
        #     )
        # '''

        versionSelector='''
            SELECT DISTINCT {timeCol} AS deprecated
            FROM {typeTable}
            WHERE {idCol} = '{id}'
            ORDER BY {timeCol} DESC limit 1 offset {recycle}
        '''

        cleaner='''
            DELETE
            FROM {typeTable}
            WHERE {idCol} = '{id}'
            AND {timeCol} <= '{deprecated}'
        '''

        if self.recycle is not None:
            deprecated=pd.read_sql_query(
                versionSelector.format(
                    typeTable    = self.typeTable.format(kind=kind),
                    idCol        = self.idCol,
                    timeCol      = self.timeCol,
                    id           = id,
                    recycle      = self.recycle
                ),
                con=self.getDB()
            )

            if deprecated.shape[0]>0:
                cleanQuery=cleaner.format(
                    typeTable    = self.typeTable.format(kind=kind),
                    idCol        = self.idCol,
                    timeCol      = self.timeCol,
                    id           = id,
                    deprecated   = deprecated.deprecated.iloc[0],
                    recycle      = self.recycle
                )

                self.getLogger().debug(f'Clean old cache entries as {cleanQuery}')
                self.getDB().execute(cleanQuery)



    def set(self, kind, id, data):
        """
        kind leads to table DataCache_{kind}

        id is written to column __DataCache_id

        Current time is written to column __DataCache_time
        """

        d=data.copy()

        columns=list(d.columns)

        d[self.idCol]=id
        now=pd.Timestamp.utcnow()
        d[self.timeCol]=now


        self.getLogger().info(f'Set cache to kind={kind}, id={id}, time={now}')

        d[[self.idCol,self.timeCol] + columns].to_sql(
            self.typeTable.format(kind=kind),
            index       = False,
            if_exists   = 'append',
            chunksize   = 999,
            con         = self.getDB(),
            method      = 'multi'
        )

        self.cleanOld(kind, id)