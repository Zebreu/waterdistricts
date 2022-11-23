FROM python:3.8

RUN pip install geocoder PyMuPDF flask requests shapely

COPY . /

ENTRYPOINT ["python", "server.py"]