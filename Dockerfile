FROM dawn001/z_mirror:hk_main

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

COPY . .
RUN rm -rf Dockerfile heroku.yml LICENSE README.md
RUN pip install --upgrade yt-dlp

CMD ["bash", "start.sh"]