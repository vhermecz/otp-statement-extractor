FROM python:3.9
ENV PYTHONDONTWRITEBYTECODE 1
RUN mkdir /app
WORKDIR /app
ADD requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
