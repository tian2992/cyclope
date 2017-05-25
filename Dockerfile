FROM	debian:9


# ENV CYCLOPE_VERSION 3

# Prevent some error messages
ENV DEBIAN_FRONTEND noninteractive

RUN		apt-get -y update && apt-get -y upgrade

# Install all prerequisites
RUN   apt-get -y install python python-pip python-dev
RUN   pip install cyclope3  


EXPOSE	8000

RUN cyclopeproject /cyclopeproject

VOLUME /cyclope_proyect

CMD python /cyclope_proyect/manage.py runserver 0.0.0.0 8000

