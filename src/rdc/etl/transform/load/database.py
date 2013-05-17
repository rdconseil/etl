# -*- coding: utf-8 -*-
#
# Author: Romain Dorgueil <romain@dorgueil.net>
# Copyright: © 2011-2013 SARL Romain Dorgueil Conseil
#
from sqlalchemy import MetaData, Table
from werkzeug.utils import cached_property
from rdc.etl.transform import Transform
from rdc.etl.util import now

class DatabaseLoad(Transform):
    table_name = None
    fetch_columns = None
    discriminant = ('id', )
    created_at_field = 'created_at'
    updated_at_field = 'updated_at'

    def __init__(self, engine, table_name=None, fetch_columns=None, discriminant=None, created_at_field=None, updated_at_field=None):
        super(DatabaseLoad, self).__init__()
        self.engine = engine
        self.table_name = table_name or self.table_name

        self.fetch_columns = {}
        if isinstance(fetch_columns, list): self.add_fetch_column(*fetch_columns)
        elif isinstance(fetch_columns, dict): self.add_fetch_column(**fetch_columns)

        self.discriminant = discriminant or self.discriminant
        self.created_at_field = created_at_field or 'created_at'
        self.updated_at_field = updated_at_field or 'updated_at'

    def get_existing_keys(self, dataset):
        keys = dataset.keys()
        column_names = self.table.columns.keys()
        return [key for key in keys if key in column_names]

    @cached_property
    def metadata(self):
        return MetaData()

    @cached_property
    def table(self):
        return Table(self.table_name, self.metadata, autoload=True, autoload_with=self.engine)

    def find(self, dataset):
        query = 'SELECT * FROM ' + self.table_name + ' WHERE ' + (' AND '.join([key_atom + ' = %s' for key_atom in self.discriminant])) + ' LIMIT 1;'
        rp = self.engine.execute(query, [dataset.get(key_atom) for key_atom in self.discriminant])

        return rp.fetchone()

    def add_fetch_column(self, *columns, **aliased_columns):
        self.fetch_columns.update(aliased_columns)
        for column in columns:
            self.fetch_columns[column] = column

    @property
    def now(self):
        return now()

    def transform(self, hash):
        row = self.find(hash)

        now = self.now
        column_names = self.table.columns.keys()
        if self.updated_at_field in column_names:
            hash.set(self.updated_at_field, now)
        else:
            if hash.has(self.updated_at_field):
                hash.remove(self.updated_at_field)

        if row:
            dataset_keys = self.get_existing_keys(hash)
            query = 'UPDATE ' + self.table_name + ' SET ' + ', '.join(['%s = %%s' % (col, ) for col in dataset_keys if not col in self.discriminant]) + ' WHERE ' + (' AND '.join([key_atom + ' = %s' for key_atom in self.discriminant]))
            values = [hash.get(col) for col in dataset_keys if not col in self.discriminant] + [hash.get(col) for col in self.discriminant]
        else:
            if self.created_at_field in column_names:
                hash.set(self.created_at_field, now)
            else:
                if hash.has(self.created_at_field):
                    hash.remove(self.created_at_field)
            dataset_keys = self.get_existing_keys(hash)
            query = 'INSERT INTO ' + self.table_name + ' (' + ', '.join(dataset_keys) + ') VALUES (' + ', '.join(['%s' for col in dataset_keys]) + ')'
            values = [hash.get(key) for key in dataset_keys]

        self.engine.execute(query, values)

        if self.fetch_columns and len(self.fetch_columns):
            if not row:
                row = self.find(hash)
            if not row:
                raise ValueError('Could not find matching row after load.')

            for alias, column in self.fetch_columns.items():
                hash.set(alias, row[column])

        yield hash