import pika
import requests


# Configuration
DOMAIN = 'example.com'
MAILGUN_API_KEY = 'YOUR_MAILGUN_API_KEY'
RABBITMQ_HOST = 'localhost'

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST)
)
channel = connection.channel()
channel.queue_declare(queue='welcome_queue', durable=True)


class Error(Exception):
    pass


class MailgunError(Error):
    def __init__(self, message):
        self.message = message


def send_welcome_message(ch, method, properties, body):
    address = body.decode('UTF-8')
    print("Sending welcome email to {}".format(address))
    res = requests.post(
        "https://api.mailgun.net/v3/{}/messages".format(DOMAIN),
        auth=("api", MAILGUN_API_KEY),
        data={"from": "Flaskr <noreply@{}>".format(DOMAIN),
              "to": [address],
              "subject": "Welcome to Flaskr!",
              "text": "Welcome to Flaskr, your account is now active!"}
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)
    if res.status_code != 200:
        # Something terrible happened :-O
        raise MailgunError("{}-{}".format(res.status_code, res.reason))


channel.basic_consume(send_welcome_message, queue='welcome_queue')
channel.start_consuming()
