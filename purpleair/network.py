"""
PurpleAir API Client Class
"""


import json
import time
from json.decoder import JSONDecodeError
from typing import List, Optional

import pandas as pd
import requests

from .api_data import API_ROOT
from .sensor import Sensor


class SensorList():
    """
    PurpleAir Sensor Network Representation
    """

    def __init__(self, parse_location=False):
        self.parse_location = parse_location

        self.data = {}
        self.get_all_data()  # Populate `data`

        self.all_sensors: List[Sensor] = []
        self.generate_sensor_list()  # Populate `all_sensors`

        # Commonly requested/used filters
        self.outside_sensors: List[Sensor] = [
            s for s in self.all_sensors if s.location_type == 'outside']
        self.useful_sensors: List[Sensor] = [
            s for s in self.all_sensors if s.is_useful()]

    def get_all_data(self) -> None:
        """
        Get all data from the API
        """
        response = requests.get(f'{API_ROOT}')
        try:
            data = json.loads(response.content)
        except JSONDecodeError as err:
            raise ValueError(
                'Invalid JSON data returned from network!') from err

        # Handle rate limit or other error message
        if 'results' not in data:
            message = data.get('message')
            error_message = message if message is not None else data
            raise ValueError(
                f'No sensor data returned from PurpleAir: {error_message}')

        self.parse_raw_result(data['results'])
        print(f"Initialized {len(self.data):,} sensors!")

    def parse_raw_result(self, flat_sensor_data: dict) -> None:
        """
        O(2n) algorithm to build the network map
        """
        out_l: List[List[dict]] = []

        # First pass: build map of parent and child sensor data
        parent_map = {}
        child_map = {}
        for sensor in flat_sensor_data:
            if 'ParentID' in sensor:
                child_map[sensor['ID']] = sensor
            else:
                parent_map[sensor['ID']] = sensor

        # Second pass: build list of complete sensors
        for child_sensor_id in child_map:
            parent_sensor_id = child_map[child_sensor_id]['ParentID']
            if parent_sensor_id not in parent_map:
                # pylint: disable=line-too-long
                raise ValueError(
                    f'Child {child_sensor_id} lists parent {parent_sensor_id}, but parent does not exist!')
            channels = [
                parent_map[parent_sensor_id],
                child_map[child_sensor_id]
            ]
            # Any unused parents will be left over
            del parent_map[parent_sensor_id]
            out_l.append(channels)

        # Handle remaining parent sensors
        for remaining_parent in parent_map:
            channels = [
                parent_map[remaining_parent],
            ]
            out_l.append(channels)

        self.data = out_l

    def generate_sensor_list(self) -> None:
        """
        Generator for Sensor objects, delated if `parse_location` is true per Nominatim policy
        """
        if self.parse_location:
            # pylint: disable=line-too-long
            print('Warning: location parsing enabled! This reduces sensor parsing speed to less than 1 per second.')
        for sensor in self.data:
            if self.parse_location:
                # Required by https://operations.osmfoundation.org/policies/nominatim/
                time.sleep(1)
            # sensor[0] is always the parent sensor
            self.all_sensors.append(Sensor(sensor[0]['ID'],
                                           json_data=sensor,
                                           parse_location=self.parse_location))

    def to_dataframe(self,
                     sensor_filter: str,
                     channel: str) -> pd.DataFrame:
        """
        Converts dictionary representation of a list of sensors to a Pandas DataFrame
        where sensor_group determines which group of sensors are used
        """
        if channel not in {'a', 'b'}:
            raise ValueError(
                f'Invalid sensor channel: {channel}. Must be in {{"a", "b"}}')

        try:
            sensor_data: pd.DataFrame = {
                'all': pd.DataFrame([s.as_flat_dict(channel)
                                     for s in self.all_sensors]),
                'outside': pd.DataFrame([s.as_flat_dict(channel)
                                         for s in [s for s in self.all_sensors
                                                   if s.location_type == 'outside']]),
                'useful': pd.DataFrame([s.as_flat_dict(channel)
                                        for s in [s for s in self.all_sensors if s.is_useful()]]),
            }[sensor_filter]

        except KeyError as err:
            raise KeyError(
                f'Invalid sensor filter supplied: {sensor_filter}') from err
        sensor_data.index = sensor_data.pop('id')
        return sensor_data
