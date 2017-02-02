import kivy
kivy.require('1.9.1')
from kivy.clock import Clock
from kivy.uix.anchorlayout import AnchorLayout
from kivy.app import App
from kivy.lang import Builder
from kivy.properties import StringProperty, Clock, NumericProperty,\
    DictProperty, BooleanProperty
import base64
from kivy.network.urlrequest import UrlRequest


class ZbarQrcodeDetector(AnchorLayout):
    login = StringProperty(u'')
    password = StringProperty(u'')
    host = StringProperty('')


    def _get_auth(self):
        # Encodes basic authorization data
        cred = ('%s:%s' % (self.login, self.password))
        return 'Basic %s' %\
               base64.b64encode(cred.encode('ascii')).decode('ascii')


    def _send_request_dzyk(self, url, success=None, error=None, params=None):
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-type': 'application/json',
            'Authorization': self._get_auth()
        }


        UrlRequest(
            url= self.host[:-14]+'com/' + url, timeout=30, req_headers=headers,
            req_body=None if params is None else dumps(params),
            on_success=success, on_error=error, on_failure=error)

    def _get_commands_error_dzyk(self, request, error):
        print  error



    def _get_commands_result_dzyk_balance_allsum(self, request, response):
        # Parses API-call response
        try:
            for i in  response:
                #self.labell.text =i['sum']
                print i
        except Exception as e:
            self._get_commands_error_dzyk(request, str(e))




    def _examplefunc(self):
        self._send_request_dzyk(
            'bal_sum/', params=None,
            success=self._get_commands_result_dzyk_balance_allsum, error=self._get_commands_error_dzyk)


    def __init__(self, **kwargs):
        super(ZbarQrcodeDetector, self).__init__(**kwargs)
        # my code
        #
        #
        def Course_thread(dt):
            self._examplefunc()
            print "r"
            #self.examplefunc("rrrr")

            #self._send_request_dzyk(
            #    'bal_sum/', params=None,
            #    success=self._get_commands_result_dzyk_balance_allsum, error=self._get_commands_error_dzyk)


        Clock.schedule_interval(Course_thread, 1)


if __name__ == '__main__':

    qrcode_kv = '''
BoxLayout:
    orientation: 'vertical'

    ZbarQrcodeDetector:
        id: detector

    Label:
        size_hint_y: None
        height: '100dp'

    BoxLayout:
        size_hint_y: None
        height: '48dp'

        Button:
            text: 'Scan a qrcode'
        Button:
            text: 'Stop detection'
'''

    class QrcodeExample(App):
        def build(self):
            return Builder.load_string(qrcode_kv)

    QrcodeExample().run()
