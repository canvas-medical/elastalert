import json

import requests

from requests.exceptions import RequestException

from .alerts import Alerter, BasicMatchString, DateTimeEncoder
from .util import EAException, elastalert_logger


class SlackFormattedMatchString(BasicMatchString):
    def _add_match_items(self):
        match_items = self.match.items()
        match_items.sort(key=lambda x: x[0])
        for key, value in match_items:
            if key.startswith('top_events_'):
                continue
            if key in ['@timestamp', '_index']:
                continue
            value_str = unicode(value)
            if type(value) in [list, dict]:
                try:
                    value_str = self._pretty_print_as_json(value)
                except TypeError:
                    # Non serializable object, fallback to str
                    pass
            self.text += '*%s:* %s\n' % (key, value_str)


class SlackAlerter(Alerter):
    """ Creates a Slack room message for each alert """
    required_options = frozenset(['slack_webhook_url'])

    def __init__(self, rule):
        super(SlackAlerter, self).__init__(rule)

        self.slack_webhook_url = self.rule['slack_webhook_url']

        if isinstance(self.slack_webhook_url, basestring):
            self.slack_webhook_url = [self.slack_webhook_url]

        self.slack_proxy = self.rule.get('slack_proxy', None)
        self.slack_username_override = self.rule.get('slack_username_override', 'elastalert')
        self.slack_channel_override = self.rule.get('slack_channel_override', '')
        self.slack_emoji_override = self.rule.get('slack_emoji_override', ':ghost:')
        self.slack_icon_url_override = self.rule.get('slack_icon_url_override', '')
        self.slack_msg_color = self.rule.get('slack_msg_color', 'danger')
        self.slack_parse_override = self.rule.get('slack_parse_override', 'none')
        self.slack_text_string = self.rule.get('slack_text_string', '')

    def format_body(self, body):
        # https://api.slack.com/docs/formatting
        body = body.encode('UTF-8')
        # body = body.replace('&', '&amp;')
        # body = body.replace('<', '&lt;')
        # body = body.replace('>', '&gt;')
        return body

    def create_alert_body(self, matches):
        body = self.get_aggregation_summary_text(matches)
        for match in matches:
            body += unicode(SlackFormattedMatchString(self.rule, match))
            # Separate text of aggregated alerts with dashes
            if len(matches) > 1:
                body += '\n----------------------------------------\n'
        return body

    def alert(self, matches):
        body = self.create_alert_body(matches)

        body = self.format_body(body)
        # post to slack
        headers = {'content-type': 'application/json'}
        # set https proxy, if it was provided
        proxies = {'https': self.slack_proxy} if self.slack_proxy else None

        payload = {
            'username': self.slack_username_override,
            'channel': self.slack_channel_override,
            'parse': self.slack_parse_override,
            'text': self.slack_text_string,
            'attachments': [
                {
                    'color': self.slack_msg_color,
                    'title': self.create_title(matches),
                    'text': body,
                    'fields': []
                }
            ]
        }

        if self.slack_icon_url_override != '':
            payload['icon_url'] = self.slack_icon_url_override
        else:
            payload['icon_emoji'] = self.slack_emoji_override

        for url in self.slack_webhook_url:
            try:
                response = requests.post(url, data=json.dumps(payload, cls=DateTimeEncoder), headers=headers, proxies=proxies)
                response.raise_for_status()
            except RequestException as e:
                raise EAException("Error posting to slack: %s" % e)

        elastalert_logger.info("Alert sent to Slack")

    def get_info(self):
        return {'type': 'slack',
                'slack_username_override': self.slack_username_override,
                'slack_webhook_url': self.slack_webhook_url}
