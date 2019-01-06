from mailin import Mailin

import config


class Mailer:
    def __init__(self, api_key):
        self.mailin = Mailin("https://api.sendinblue.com/v2.0",
                             api_key,
                             timeout=5)

    def send_mail(self, parameters):
        data = {
            "to": {"example@example.com": "Kate Test"},
            "bcc": {"example@example.com": "Andrei Test"},
            "from": ["example@example.com", "Andrei Test"],
            "subject": "testtttt",
            "html": "This is the <h1>test HTML</h1>",
            "attachment": [
                "https://domain.com/path-to-file/filename1.pdf",
                "https://domain.com/path-to-file/filename2.jpg"
            ]
        }

        result = self.mailin.send_email(data)
        print(result)
