# gpx-interval
This is a python script that analyzes a .gpx file from a GPS device to find the fastest interval of a given length. 
GPX is a standard format for representing a GPS track.

To run this script you will need a Python environment and the ability to install additional packages that the script requires.

The interval can be specified in distance units, in which case it finds the segment in which the specified distance is covered in the 
least amount of time, or in time units, in which case it finds the segment in which the greatest distance is covered in specified time.

Here's an example:. Let's say we want to find the fastest mile in a GPX file called mytrack.gpx: 

    $ python gpx-interval.py  -interval 1mi mytrack.gpx
   
    parsed file: mytrack.gpx
    processed 65061 points
    date: 2024-11-27 14:25:46PM (UTC-0600, CST)
    track distance: (3d): 19209.3 m
    track time: 3585.9 sec

    target interval: 1 mi (1609.3 m):
       start: 14:33:06 (T+00:07:19) (index=7936)
       end: 14:35:58 (T+00:10:12) (index=11056)
       time: 172.41 sec
       distance: 1609.8 m (1.000 mi)
       speed: 9.34 m/s (20.89 mph)

Some additional notes:
- The -interval option specifies the interval(s). It can be abbreviated as -i. Multiple intervals can be specified. For
example `-i 1mi -i 1hr` would find both the fastest mile and the most distance covered in any 1-hour stretch.
Distance units can be any of 'ft' (feet), 'yd' (yards), 'm' (meters), 'mi' (miles), or 'nm' (nautical miles). Time units can be any of 'sec', 'min', or 'hr'.

- The option '-2d' causes altitude readings from the GPS to be ignored. This is useful for increased accuracy at constant altitudes
(such as on water) since altitude from most GPS devices is not very accurate.

- The start and end times shown in the output are relative to the start of the track. This can be useful if you have (say) video from the 
track so you can locate the fastest interval(s) in the video.

- This script was built using Python 3.10.12. It requires a python environment and several packages. It was tested with GPX files from a
GoPro Hero9 and a Wahoo ELEMNT Bolt bike computer.

I built this script in response to the Facebook group <a href="https://www.facebook.com/share/g/15GXCqTEEH/" target="_blank">Catamaran Speed Sailing Challenge</a>. 
I was using a GPS-enabled GoPro camera and did not have a good way to process the GPS data.

A great tool to process files from a GoPro is <a href="https://github.com/time4tea/gopro-dashboard-overlay" target="_blank">this one</a>. It includes a tool 
to extract the GPS data from the camera into a GPX file.

Credit for the original version of this script goes to <a href="https://www.wouternieuwerth.nl/how-to-find-the-fastest-section-within-a-gpx-file-with-python-jupyter-notebooks/" target="_blank">Wouter Nieuwerth</a>.
