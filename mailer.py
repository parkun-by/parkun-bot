from mailin import Mailin

import config


class Mailer:
    def __init__(self, api_key):
        self.mailin = Mailin("https://api.sendinblue.com/v2.0",
                             api_key,
                             timeout=5)

    def send_mail(self, parameters):
        subject = 'Обращение о нарушении правил остановки и стоянки ' +\
                  'транспортных средств'

        data = {
            'to': parameters['to'],
            'bcc': parameters['bcc'],
            'from': parameters['from'],
            'subject': subject,
            'html': parameters['html'],
            'attachment': parameters['attachment']
        }

        # TODO разобрать это вот и написать на асинхронных реквестах
        result = self.mailin.send_email(data)

        if result['code'] != 'success':
            raise Exception(str(result))
