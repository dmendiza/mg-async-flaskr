import pika
import requests


_DELIVERY_MODE_PERSISTENT=2

# Configuration
DOMAIN = 'example.com'
MAILGUN_API_KEY = 'YOUR_MAILGUN_API_KEY'
RABBITMQ_HOST = 'localhost'
RETRY_DELAY_MS = 30000

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST)
)
channel = connection.channel()
channel.queue_declare(queue='welcome_queue', durable=True)

retry_channel = connection.channel()
retry_channel.queue_declare(
    queue='retry_queue',
    durable=True,
    arguments={
        'x-message-ttl': RETRY_DELAY_MS,
        'x-dead-letter-exchange': 'amq.direct',
        'x-dead-letter-routing-key': 'welcome_queue'
    }
)


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
        print("Error sending to {}. {} {}. Retrying...".format(
            address, res.status_code, res.reason
        ))
        retry_channel.basic_publish(
            exchange='',
            routing_key='retry_queue',
            body=address,
            properties=pika.BasicProperties(
                delivery_mode=_DELIVERY_MODE_PERSISTENT
            )
        )


channel.basic_consume(send_welcome_message, queue='welcome_queue')
channel.start_consuming()
