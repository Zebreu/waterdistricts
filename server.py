import os
import json
import difflib
import urllib.request

import geocoder
import fitz
from flask import Flask, request
import requests
import shapely
from shapely import geometry

census_geocode_url =  'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'

#online_pdf_location = 'https://www.nmhealthysoil.org/wp-content/uploads/2022/05/NMACD_Directory.pdf'
online_pdf_location = 'https://www.nmhealthysoil.org/wp-content/uploads/2023/02/NMACD-2023-Directory-Rev-2-8-2023.pdf'
filepath = 'NMACD_Directory.pdf'

urllib.request.urlretrieve(online_pdf_location, filepath)

app = Flask(__name__)

with open('NM_Soil_Water_Conservation_Districts.geojson') as opened:
    shape_dictionaries = json.load(opened)

geometries = []
names = []
for shape in shape_dictionaries['features']:
    geometries.append(shapely.geometry.shape(shape['geometry']))
    names.append(shape['properties']['NAME'])

with open('widget.html', 'r') as opened:
    homepage = opened.read()
    actual_url = os.getenv('RENDER_EXTERNAL_URL')
    homepage = homepage.replace('placeholder_url', actual_url)

def parse_pdf():
    """Most of the esoteric lines here are about ignoring districts with 2 pages of information
    and any other pages without contact information"""
    doc = fitz.open(filepath)  
    pages = []
    for page in doc:  
        text = page.get_text()
        pages.append(text)
    doc.close()

    contents = []
    for page in pages:   
        content = []
        relevant = True
        if 'Position:' in page and "Start Date" in page and "Term Expires" in page and "Phone:" in page:
            if "Page 2" in page:
                continue
            for p in page.split('\n'):
                line = p.strip()
                if line != '':
                    if line == "Position:":
                        relevant = False
                    if relevant and line != 'Soil and Water Conservation Districts':
                        content.append(line)
            contents.append(content[1:])
    
    districts = {}
    for content in contents:
        name = content[0][:-5]
        districts[name] = '<br>'.join(content).replace(':<br>', ': ')

    return districts

district_info = parse_pdf()

def geocode(address):
    try:    
        response = geocoder.osm(address)
        if response.status == 'OK':
            point = shapely.geometry.Point(response.json['lng'], response.json['lat']) # shapefile is in CRS 84
            matched = response.json['address']
            print('osm')
            return point, matched
    except:
        pass 

    try: 
        census_address = '+'.join(address.split(' ')).replace(',','%2C').replace('#','')
        print(census_address)
        census_response = requests.get(census_geocode_url+f'?address={census_address}&benchmark=2020&format=json')
        print(census_response.json())
        if len(census_response.json()['result']['addressMatches']) > 0:
            coords = census_response.json()['result']['addressMatches'][0]['coordinates']
            point = shapely.geometry.Point(coords['x'],coords['y'])
            print('census')
            return point, ''
    except:
        pass

    return 'Unknown', 'Unknown'

def get_region(point):
    region = 'Unknown'
    distances = []
    for name, border_geometry in zip(names, geometries):
        if border_geometry.contains(point):
            region = name
            break
        distances.append((point.distance(border_geometry),name))

    if region == 'Unknown':
        region = sorted(distances)[0][1] # (distance, name)

    return region

def get_region_info(name):
    if name in district_info:
        return district_info[name]
    
    closest = difflib.get_close_matches(name, list(district_info.keys()), n=1, cutoff=0.1)
    return district_info[closest[0]]

def try_to_fix_address(address):
    # remove Unit XX from the request
    index = address.lower().find('unit ')
    print(index)
    if index > -1:
        space = address[index+5:].find(' ')
        if space == -1:
            space = address[index+5:].find(',')
            
        new_address = address[0:index]+address[space+index+5:]
        return geocode(new_address)
    else:
        return 'Unknown', 'Unknown'


@app.route('/')
def home():
    return homepage


@app.route('/gps_district', methods=['POST', 'GET'])
def get_district_from_gps():
    # example 45.395178570689815, -75.75054373745539
    lat, lon = request.form['gps'].split(',')
    
    print(lat,lon)
    
    point = shapely.geometry.Point(lon, lat)
    
    print('Calculating nearest district')
    region = get_region(point)
    print(region)
    result_info = get_region_info(region)

    result = f"Information about your Soil and Water Conservation District:<br> {result_info}"
    return result


@app.route('/district', methods=['POST', 'GET'])
def get_district():
    street = request.form['street']
    city = request.form['city']
    zipcode = request.form['zipcode']
    address = f'{street}, {city}, NM {zipcode}, USA'
    
    print(address)
    print('Geocoding request')
    point, matched = geocode(address)
    if point == "Unknown":
        point, matched = try_to_fix_address(address)
        if point == "Unknown":
            return "Sorry, this address could not be found. You may want to try writing your address differently. You can also email info@nmhealthysoil.org to ask for information"

    print('Calculating nearest district')
    region = get_region(point)
    print(region)
    result_info = get_region_info(region)

    result = f"Matched address: {matched} <br>Information about your Soil and Water Conservation District:<br> {result_info}"
    return result


port = os.getenv('PORT')
app.run(host='0.0.0.0', port=port)
