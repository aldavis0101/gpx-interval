# gpx-interval.py - find fastest interval(s) of given length from GPX file
#
# usage: python gpx-interval.py [-2d] [-interval NN.<unit>] <file>.gpx
#   where <unit> is one of ft, yd, mi, m, km

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

# Target interval lengths - defaults to 100m, 1 mile, 5 miles
default_intervals = ['100m', '1mi', '5mi']
# If true, ignore altitude data to avoid skewing distances. For e.g. sailing
use_2d = False

# Helper class to represent an interval specified with various units
class Interval:
  # table to convert from meters to unit
  conv_table = {'ft' : 3.28084, 
                'yd' : 1.093613,
                'mi' : 0.0006213712,
                'm'  : 1.0,
                'km' : .001};
  def __init__(self, init_str):
    m = re.match('([0-9]+)(ft|yd|mi|m|km)', init_str)
    if not m:
       raise ValueError('interval specification should be NNN.[ft|yd|mi|m|km]')
    self.value = int(m[1])
    self.unit = m[2]   
  def __str__(self):
    return str(self.value) + ' ' + self.unit
  def to_meters(self):
    return self.value / self.conv_table[self.unit]

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
# Parse the file and create a table from the data
def read_gpx(filename):
  # Read all the points from all tracks in the GPX file
  points = []
  for file in [filename]:
    gpx_file = open(filename, 'r')
    gpx = gpxpy.parse(gpx_file)
    print("parsed file: ", filename)

    for segment in gpx.tracks[0].segments: # all segments
      data = segment.points
      for point in data:
        points.append({'lon': point.longitude, 
                       'lat' : point.latitude, 
                       'alt' : point.elevation, 
                       'timestamp' : point.time})
        #print(points)
  print("processed ", len(points), " points")

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

  # Create column with values that are 'shifted' one forwards, so we can 
  # create calculations for differences.
  df['lon-start'] = df['lon']
  df['lon-start'] = np.roll(df['lon-start'], 1)
  df['lat-start'] = df['lat']
  df['lat-start'] = np.roll(df['lat-start'], 1)
  df['alt-start'] = df['alt']
  df['alt-start'] = np.roll(df['alt-start'], 1)

  df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

  # Add columns with time and distance deltas
  df['elapsed_time'] = df.apply(
      lambda x: (x['timestamp'] - df['timestamp'].iloc[0]).total_seconds(), 
      axis=1)
  df['distance_dis_2d'] = df.apply(
      lambda x: distance.distance((x['lat-start'], x['lon-start']), 
                                  (x['lat'], x['lon'])).m, 
      axis = 1)
  df['alt_dif'] = df.apply(
      lambda x: x['alt-start'] - x['alt'], 
      axis=1)
  df['distance_dis_3d'] = df.apply(
      lambda x: sqrt(x['distance_dis_2d']**2 + (x['alt_dif'])**2), 
      axis=1)

  df.at[0, 'distance_dis_2d'] = 0
  df.at[0, 'distance_dis_3d'] = 0
  df.at[0, 'alt_dif'] = 0

  # Use 2d or 3d distance to calculate cumulative distance at each point
  distance_tag = 'distance_dis_2d' if use_2d else 'distance_dis_3d'
  df['elapsed_distance'] = df[distance_tag].cumsum()

  # Create a column with timestamp converted to local time, for reporting
  #df['ts_local'] = df['timestamp'].dt.tz_convert(tz.tzlocal())
  tzname = tzf.timezone_at(lng=df['lon'].iloc[0], lat=df['lat'].iloc[0])
  tz = dateutil.tz.gettz(tzname)
  df['ts_local'] = df['timestamp'].dt.tz_convert(tz)

  # Report some info from the file
  filedate = df['ts_local'].iloc[0]
  print(f"date: {filedate.strftime('%Y-%m-%d %H:%M:%S%p (UTC%z, %Z)')}")
  print(f"total distance: {df['elapsed_distance'].iloc[-1]:.1f} m", end=' ')
  print(f"({'2d' if use_2d else '3d'})")
  print(f"total time: {df['elapsed_time'].iloc[-1]:.1f} sec")

#################################################################################
# Find fastest interval equal to or exceeding the given target
def find_best_interval(interval):
  target_interval = interval.to_meters()
  print(f"\ntarget interval: {interval} ({target_interval:.1f} m):")

  # Skip if the total distance of the track is smaller then the target
  if df['elapsed_distance'].iloc[-1] < target_interval:
      print("no intervals found (track too short)")
      return

  # Iterate over points in the track. From each point (i), find the first point (j)
  # with least as much delta distance as the target interval. Record the interval
  # with the best speed.
  best_interval = {'start': None, 'end': None, 'speed': None }
  j = 1
  for i in range(len(df.index)-2):
      j = max(j, i+1)
      while j < len(df.index):
          dist = df['elapsed_distance'].iloc[j] - df['elapsed_distance'].iloc[i]
          if dist < target_interval:
              j = j + 1
          else:
              elapsed = df['elapsed_time'].iloc[j] - df['elapsed_time'].iloc[i]
              speed = dist / elapsed
              if best_interval['start'] == None or speed > best_interval['speed']:
                  best_interval.update({'start': i, 'end': j, 'speed': speed})
              # note: don't advance j, since [i+1,j] could be a candidate
              break

  # This should not happen; if track is long enough there should be at least 
  # one interval
  if not best_interval['start']:
      print("no interval found")
      return

  # Report results from the winning interval 
  [start_idx, end_idx] = [best_interval['start'], best_interval['end']]
  [start_point, end_point] = [df.loc[start_idx], df.loc[end_idx]]
  speed = best_interval['speed']
  distance = end_point['elapsed_distance'] - start_point['elapsed_distance']
  elapsed = end_point['elapsed_time'] - start_point['elapsed_time']

  print(f"start={start_point['ts_local'].strftime('%H:%M:%S')}", end=' ')
  print(f"(T+{time.strftime('%H:%M:%S', time.gmtime(start_point['elapsed_time']))})", end=' ')
  print(f"(index={start_idx})")
  print(f"end={end_point['ts_local'].strftime('%H:%M:%S')}", end=' ')
  print(f"(T+{time.strftime('%H:%M:%S', time.gmtime(end_point['elapsed_time']))})", end=' ')
  print(f"(index={end_idx})")
  print(f"time={elapsed:.2f} sec")
  print(f"dist={distance:.1f} m ({distance*0.0006213712:.3f} mi)" )
  print(f"speed={speed:.2f} m/s ({speed*0.0006213712*3600:.2f} mph)")

if __name__ == "__main__":
    main()
