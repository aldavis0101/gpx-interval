# gpx-interval.py - find fastest interval(s) of given length or time from GPX file
#
# usage: python gpx-interval.py [-2d] [-interval NN.<unit>] <file>.gpx
#   where <unit> is one of ft, yd, mi, m, km, sec, min, hr

# Adapted from https://www.wouternieuwerth.nl/how-to-find-the-fastest-section-within-a-gpx-file-with-python-jupyter-notebooks/

import argparse
import re
import gpxpy
from geopy import distance
from math import sqrt
import pandas as pd
import numpy as np
import datetime
import dateutil
import time
from timezonefinder import TimezoneFinder

tzf = TimezoneFinder() 

# Default target interval lengths if not specified
default_intervals = ['100m', '1mi', '5mi']
# If true, ignore altitude data to avoid skewing distances. For e.g. sailing
use_2d = False

#################################################################################
# Helper class to represent an interval specified with various units
class Interval:
  # table to classify and normalize units
  # - factor converts distance to meters and time to seconds
  unit_table = {'ft' : { 'type' : 'distance', 'factor' : 3.28084 }, 
                'yd' : { 'type' : 'distance', 'factor' : 1.093613 },
                'mi' : { 'type' : 'distance', 'factor' : 0.0006213712 },
                'm'  : { 'type' : 'distance', 'factor' : 1.0 },
                'km' : { 'type' : 'distance', 'factor' : .001 }, 
                'sec': { 'type' : 'time',     'factor' : 1.0 }, 
                'min': { 'type' : 'time',     'factor' : 0.0166666667 },
                'hr' : { 'type' : 'time',     'factor' : 0.0002777778 } }
  # construct an interval from a string
  def __init__(self, init_str):
    for unit in Interval.unit_table.keys():
       m = re.fullmatch('([0-9]+)' + unit, init_str)
       if (m):
          self.value = int(m[1])
          self.unit = unit
          self.is_distance = Interval.unit_table[unit]['type'] == 'distance'
          return
    valid_units = '|'.join(Interval.unit_table.keys())
    raise ValueError('interval specification should be NNN.[' + valid_units + ']')
  # normalize interval: distance to meters, time to seconds
  def normalize(self):
    return self.value / Interval.unit_table[self.unit]['factor']
  def __str__(self):
    normalized_units = 'm' if self.is_distance else 'sec'
    return f"{self.value} {self.unit} ({self.normalize():.1f} {normalized_units})"


#################################################################################
def main():
  # argparse helper to convert -interval option to Interval type
  def validate_interval(arg):
    try:
      iv = Interval(arg)
    except ValueError as error:
      raise argparse.ArgumentTypeError(error)
    return iv

  parser = argparse.ArgumentParser(
      description='Find best interval from GPX file')

  parser.add_argument('-2d', dest='option2d', action='store_true',
                      help='ignore GPS altitude')
  parser.add_argument('-i', '-interval', dest='intervals', action='append', 
                      type=validate_interval,
                      help='specify target interval(s)')
  parser.add_argument('filename', type=argparse.FileType('r'),
                      help='name of .gpx file')
  args = parser.parse_args()
  global use_2d
  use_2d = args.option2d
  global target_intervals
  target_intervals = args.intervals if args.intervals \
    else [ Interval(i) for i in default_intervals ] 
 
  filename = args.filename.name
  read_gpx(filename)
  for interval in target_intervals:
    find_best_interval(interval)

#################################################################################
# Parse the file and set up a pandas table that will be used for processing
def read_gpx(filename):
  # Read all the points from all tracks in the GPX file
  points = []
  for file in [filename]:
    gpx_file = open(filename, 'r')
    gpx = gpxpy.parse(gpx_file)
    print(f"parsed file: {filename}")

    for segment in gpx.tracks[0].segments: # all segments
      data = segment.points
      for point in data:
        points.append({'lon': point.longitude, 
                       'lat' : point.latitude, 
                       'alt' : point.elevation, 
                       'timestamp' : point.time})
        #print(points)
  print(f"processed {len(points)} points")

  if len(points) == 0:
    print("empty track")
    return

  # Build a pandas datafrome from the GPS data
  global df
  df = pd.DataFrame(points, columns=['lon', 'lat', 'alt', 'timestamp'])
  df = df.sort_values(by=['timestamp'])
  df = df.reset_index()
  #print(df.to_string())

  df.ffill(inplace=True)
  df.bfill(inplace=True)

  # Create columns with position values shifted one point forwards, to enable
  # caclulating deltas (below)
  df['lon-start'] = df['lon']
  df['lon-start'] = np.roll(df['lon-start'], 1)
  df['lat-start'] = df['lat']
  df['lat-start'] = np.roll(df['lat-start'], 1)
  df['alt-start'] = df['alt']
  df['alt-start'] = np.roll(df['alt-start'], 1)

  df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

  # Calculate point-to-point time and distance deltas into new columns
  df['elapsed_time'] = df.apply(
      lambda x: (x['timestamp'] - df['timestamp'].iloc[0]).total_seconds(), 
      axis=1)
  df['delta_2d'] = df.apply(
      lambda x: distance.distance((x['lat-start'], x['lon-start']), 
                                  (x['lat'], x['lon'])).m, 
      axis = 1)
  df['delta_alt'] = df.apply(
      lambda x: x['alt-start'] - x['alt'], 
      axis=1)
  df['delta_3d'] = df.apply(
      lambda x: sqrt(x['delta_2d']**2 + (x['delta_alt'])**2), 
      axis=1)

  df.at[0, 'delta_2d'] = 0
  df.at[0, 'delta_3d'] = 0
  df.at[0, 'delta_alt'] = 0

  # Accumulate 2d or 3d deltas to calculate cumulative distance at each point
  distance_tag = 'delta_2d' if use_2d else 'delta_3d'
  df['elapsed_distance'] = df[distance_tag].cumsum()

  # Create a column with timestamp converted to local time, for reporting
  #df['ts_local'] = df['timestamp'].dt.tz_convert(tz.tzlocal())
  tzname = tzf.timezone_at(lng=df['lon'].iloc[0], lat=df['lat'].iloc[0])
  tz = dateutil.tz.gettz(tzname)
  df['ts_local'] = df['timestamp'].dt.tz_convert(tz)

  # Report some info from the file
  filedate = df['ts_local'].iloc[0]
  dtype = '2d' if use_2d else '3d'
  print(f"date: {filedate.strftime('%Y-%m-%d %H:%M:%S%p (UTC%z, %Z)')}")
  print(f"track distance: ({dtype}): {df['elapsed_distance'].iloc[-1]:.1f} m")
  print(f"track time: {df['elapsed_time'].iloc[-1]:.1f} sec")

#################################################################################
# Find fastest interval equal to or exceeding the given target. Interval can be
# specified as distance (eg. 1 mi) or time (eg. 1 min)
def find_best_interval(interval):
  target_interval = interval.normalize()

  # Skip if the total distance of the track is smaller then the target
  print(f"\ntarget interval: {interval}:")
  key = 'elapsed_distance' if interval.is_distance else 'elapsed_time'
  if df[key].iloc[-1] < target_interval:
    print("no intervals found (track too short)")
    return

  # Iterate over points in the track. From each point (i), find the first point (j)
  # with least as much delta distance or time as the target interval. Record the 
  # interval with the best speed.
  best_interval = {'start': None, 'end': None, 'speed': None }
  j = 1
  for i in range(len(df.index)-2):
    j = max(j, i+1)
    while j < len(df.index):
      dist = df['elapsed_distance'].iloc[j] - df['elapsed_distance'].iloc[i]
      elapsed = df['elapsed_time'].iloc[j] - df['elapsed_time'].iloc[i]
      span = dist if interval.is_distance else elapsed
      if span < target_interval:
        j = j + 1
      else:
        speed = dist / elapsed
        if best_interval['start'] is None or speed > best_interval['speed']:
          best_interval.update({'start': i, 'end': j, 'speed': speed})
        # note: don't advance j, since [i+1,j] could also be a candidate
        break

  # This should not happen; with a long-enough track there must be at least 
  # one interval
  if best_interval['start'] is None:
     print("no interval found")
     return

  # Report results from the winning interval 
  [start_idx, end_idx] = [best_interval['start'], best_interval['end']]
  [start_point, end_point] = [df.loc[start_idx], df.loc[end_idx]]
  speed = best_interval['speed']
  distance = end_point['elapsed_distance'] - start_point['elapsed_distance']
  elapsed = end_point['elapsed_time'] - start_point['elapsed_time']

  print(f"   start: {start_point['ts_local'].strftime('%H:%M:%S')}", end=' ')
  print(f"(T+{time.strftime('%H:%M:%S', time.gmtime(start_point['elapsed_time']))})", end=' ')
  print(f"(index={start_idx})")
  print(f"   end: {end_point['ts_local'].strftime('%H:%M:%S')}", end=' ')
  print(f"(T+{time.strftime('%H:%M:%S', time.gmtime(end_point['elapsed_time']))})", end=' ')
  print(f"(index={end_idx})")
  print(f"   time: {elapsed:.2f} sec")
  print(f"   distance: {distance:.1f} m ({distance*0.0006213712:.3f} mi)" )
  print(f"   speed: {speed:.2f} m/s ({speed*0.0006213712*3600:.2f} mph)")

#################################################################################
if __name__ == "__main__":
    main()
