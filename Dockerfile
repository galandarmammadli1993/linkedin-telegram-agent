FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY bot.py /app/bot.py
RUN mkdir -p /data
CMD ["python", "bot.py"]
