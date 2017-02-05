# -*- coding: utf-8 -*-

'''
Qrcode example application
==========================

Author: Mathieu Virbel <mat@meltingrocks.com>

Featuring:

- Android camera initialization
- Show the android camera into a Android surface that act as an overlay
- New AndroidWidgetHolder that control any android view as an overlay
- New ZbarQrcodeDetector that use AndroidCamera / PreviewFrame + zbar to
  detect Qrcode.

'''
import kivy
kivy.require('1.9.1')

from kivy.network.urlrequest import UrlRequest
from kivy.properties import StringProperty, Clock, NumericProperty,\
    DictProperty, BooleanProperty
from kivy.uix.button import Button
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy import metrics
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from json import dumps
import base64
# my import
from kivy.clock import Clock
from kivy.adapters.listadapter import ListAdapter
from kivy.uix.listview import ListItemButton, ListView
import time
import re

from random import randint


__version__ = '1.0'

from collections import namedtuple
from kivy.lang import Builder
from kivy.app import App
from kivy.properties import ObjectProperty, ListProperty, BooleanProperty, \
    NumericProperty
from kivy.uix.widget import Widget
from kivy.uix.anchorlayout import AnchorLayout
from kivy.graphics import Color, Line
from jnius import autoclass, PythonJavaClass, java_method, cast
from android.runnable import run_on_ui_thread

# preload java classes
System = autoclass('java.lang.System')
System.loadLibrary('iconv')
PythonActivity = autoclass('org.renpy.android.PythonActivity')
Camera = autoclass('android.hardware.Camera')
ImageScanner = autoclass('net.sourceforge.zbar.ImageScanner')
Config = autoclass('net.sourceforge.zbar.Config')
SurfaceView = autoclass('android.view.SurfaceView')
LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
Image = autoclass('net.sourceforge.zbar.Image')
ImageFormat = autoclass('android.graphics.ImageFormat')
LinearLayout = autoclass('android.widget.LinearLayout')
Symbol = autoclass('net.sourceforge.zbar.Symbol')

# my code insert
#
#
#
#
#




class PreviewCallback(PythonJavaClass):
    '''Interface used to get back the preview frame of the Android Camera
    '''
    __javainterfaces__ = ('android.hardware.Camera$PreviewCallback', )

    def __init__(self, callback):
        super(PreviewCallback, self).__init__()
        self.callback = callback

    @java_method('([BLandroid/hardware/Camera;)V')
    def onPreviewFrame(self, data, camera):
        self.callback(camera, data)


class SurfaceHolderCallback(PythonJavaClass):
    '''Interface used to know exactly when the Surface used for the Android
    Camera will be created and changed.
    '''

    __javainterfaces__ = ('android.view.SurfaceHolder$Callback', )

    def __init__(self, callback):
        super(SurfaceHolderCallback, self).__init__()
        self.callback = callback

    @java_method('(Landroid/view/SurfaceHolder;III)V')
    def surfaceChanged(self, surface, fmt, width, height):
        self.callback(fmt, width, height)

    @java_method('(Landroid/view/SurfaceHolder;)V')
    def surfaceCreated(self, surface):
        pass

    @java_method('(Landroid/view/SurfaceHolder;)V')
    def surfaceDestroyed(self, surface):
        pass


class AndroidWidgetHolder(Widget):
    '''Act as a placeholder for an Android widget.
    It will automatically add / remove the android view depending if the widget
    view is set or not. The android view will act as an overlay, so any graphics
    instruction in this area will be covered by the overlay.
    '''

    view = ObjectProperty(allownone=True)
    '''Must be an Android View
    '''

    def __init__(self, **kwargs):
        self._old_view = None
        from kivy.core.window import Window
        self._window = Window
        kwargs['size_hint'] = (None, None)
        super(AndroidWidgetHolder, self).__init__(**kwargs)

    def on_view(self, instance, view):
        if self._old_view is not None:
            layout = cast(LinearLayout, self._old_view.getParent())
            layout.removeView(self._old_view)
            self._old_view = None

        if view is None:
            return

        activity = PythonActivity.mActivity
        activity.addContentView(view, LayoutParams(*self.size))
        view.setZOrderOnTop(True)
        view.setX(self.x)
        view.setY(self._window.height - self.y - self.height)
        self._old_view = view

    def on_size(self, instance, size):
        if self.view:
            params = self.view.getLayoutParams()
            params.width = self.width
            params.height = self.height
            self.view.setLayoutParams(params)
            self.view.setY(self._window.height - self.y - self.height)

    def on_x(self, instance, x):
        if self.view:
            self.view.setX(x)

    def on_y(self, instance, y):
        if self.view:
            self.view.setY(self._window.height - self.y - self.height)


class AndroidCamera(Widget):
    '''Widget for controling an Android Camera.
    '''

    index = NumericProperty(0)

    __events__ = ('on_preview_frame', )

    def __init__(self, **kwargs):
        self._holder = None
        self._android_camera = None
        super(AndroidCamera, self).__init__(**kwargs)
        self._holder = AndroidWidgetHolder(size=self.size, pos=self.pos)
        self.add_widget(self._holder)

    @run_on_ui_thread
    def stop(self):
        if self._android_camera is None:
            return
        self._android_camera.setPreviewCallback(None)
        self._android_camera.release()
        self._android_camera = None
        self._holder.view = None

    @run_on_ui_thread
    def start(self):
        if self._android_camera is not None:
            return

        self._android_camera = Camera.open(self.index)

        # create a fake surfaceview to get the previewCallback working.
        self._android_surface = SurfaceView(PythonActivity.mActivity)
        surface_holder = self._android_surface.getHolder()

        # create our own surface holder to correctly call the next method when
        # the surface is ready
        self._android_surface_cb = SurfaceHolderCallback(self._on_surface_changed)
        surface_holder.addCallback(self._android_surface_cb)

        # attach the android surfaceview to our android widget holder
        self._holder.view = self._android_surface

    def _on_surface_changed(self, fmt, width, height):
        # internal, called when the android SurfaceView is ready
        # FIXME if the size is not handled by the camera, it will failed.
        params = self._android_camera.getParameters()
        params.setPreviewSize(width, height)
        self._android_camera.setParameters(params)

        # now that we know the camera size, we'll create 2 buffers for faster
        # result (using Callback buffer approach, as described in Camera android
        # documentation)
        # it also reduce the GC collection
        bpp = ImageFormat.getBitsPerPixel(params.getPreviewFormat()) / 8.
        buf = '\x00' * int(width * height * bpp)
        self._android_camera.addCallbackBuffer(buf)
        self._android_camera.addCallbackBuffer(buf)

        # create a PreviewCallback to get back the onPreviewFrame into python
        self._previewCallback = PreviewCallback(self._on_preview_frame)

        # connect everything and start the preview
        self._android_camera.setPreviewCallbackWithBuffer(self._previewCallback);
        self._android_camera.setPreviewDisplay(self._android_surface.getHolder())
        self._android_camera.startPreview();

    def _on_preview_frame(self, camera, data):
        # internal, called by the PreviewCallback when onPreviewFrame is
        # received
        self.dispatch('on_preview_frame', camera, data)
        # reintroduce the data buffer into the queue
        self._android_camera.addCallbackBuffer(data)

    def on_preview_frame(self, camera, data):
        pass

    def on_size(self, instance, size):
        if self._holder:
            self._holder.size = size

    def on_pos(self, instance, pos):
        if self._holder:
            self._holder.pos = pos


class ZbarQrcodeDetector(AnchorLayout):
    # my code
    #
    #
    #

    # Auth properties
    login = StringProperty(u'')
    password = StringProperty(u'')
    host = StringProperty('')
    login = 'dzyk'
    password = 'sebastopol'
    host = 'http://10.42.0.1:8000/remotecontrol/'


    # Represents the last command which was accepted
    last_accepted_command = StringProperty('')

    # Bound to the "Info" label
    info_text = StringProperty('')

    # Command execution confirmation flag
    need_confirm = BooleanProperty(True)

# my functions
#
#
#
# data for friends list

# --------------------


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




    labell = Label(id = 'text_label',text='labell', halign='center',
                             size_hint_y=None, width=metrics.dp(35))
    friendlabel = Label(id = 'friend_label',text=' click >>', halign='center',
                             size_hint_y=None, width=metrics.dp(35))
    scorelabel = TextInput(id = 'score_label',text='0.99', halign='center',
                             size_hint_y=None, width=metrics.dp(35), multiline=False)


    textinput_addfriend = TextInput(id = 'txtaddfriend',text='', multiline=False)



    def _get_commands_error_dzyk(self, request, error):
        print  error



    def _get_commands_result_dzyk_balance_allsum(self, request, response):
        # Parses API-call response
        try:
            for i in  response:
                self.labell.text =i['sum']
                self.parent.ids.labell.text = i['sum']
        except Exception as e:
            self._get_commands_error_dzyk(request, str(e))

    def _get_commands_result_dzyk_friend(self, request, response):
        try:
            self._pnl_friend.clear_widgets()
            c = 0
            for i in  response:
                if c < 10:
                    st ="%s:%s:%s"%( i['friend'],i['friend_username'],i['btcaddress_friend'])
                    self.data2[c]['text'] = st
                    c += 1

            self._pnl_friend.add_widget(self.list_view2)
            self.list_adapter2.data.prop.dispatch(self.list_adapter2.data.obj())

        except Exception as e:
            self._get_commands_error_dzyk(request, str(e))

    def gofrequest(self, request, response):
        try:
            self.friendlabel.text = response

        except Exception as e:
            self._get_commands_error_dzyk(request, str(e))



    def refresh_friends(self, instance=None):
        # Implements API-call "Get available command list"
        self._send_request_dzyk(
            'friend_get/', params=None,
            success=self._get_commands_result_dzyk_friend, error=self._get_commands_error_dzyk)

    def getonefriend(self, instance=None):
        # Implements API-call "Get available command list"
        self._send_request_dzyk(
            'getonefriend/', params=None,
            success=self.gofrequest, error=self._get_commands_error_dzyk)

    def getonefriendback(self, instance=None):
        # Implements API-call "Get available command list"
        self._send_request_dzyk(
            'getonefriendback/', params=None,
            success=self.gofrequest, error=self._get_commands_error_dzyk)

# add friend
    def callback_request(self, request, response):
        try:
            print request
        except Exception as e:
            self._get_commands_error_dzyk(request, str(e))


    def _dzyk_add_friend(self, instance=None):
        p = {'friend_btc':'this field must be a modified', 'comment':'my project'}
        px = ''

        px=str(self.textinput_addfriend.text)
        try:
            px = re.search(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',px).group(0)
        except Exception as e:
            px = '1PRpSMEd9TkjRodApnFBt2uEhGEDPVutyy'
            print e

        p['friend_btc']=px
        #^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$ p['comment']=re.search(r'^[0-9]+',sendname).group(0)
        self._send_request_dzyk(
            'add_friend/', params=p,
            success=self.callback_request, error=self._get_commands_error_dzyk)

        time.sleep(2)

# send score function
    def _dzyk_send(self, instance=None):
        p = {'friend':'1', 'score':'0.77'}
        p['score']=self.scorelabel.text
        p['friend']=self.friendlabel.text
        self._send_request_dzyk(
            'score_change/', params=p,
            success=self.callback_request, error=self._get_commands_error_dzyk)
#




    '''Widget that use the AndroidCamera and zbar to detect qrcode.
    When found, the `symbols` will be updated
    '''
    camera_size = ListProperty([600, 480])

    symbols = ListProperty([])
    dataqr = ListProperty([])

    # XXX can't work now, due to overlay.
    show_bounds = BooleanProperty(False)

    Qrcode = namedtuple('Qrcode',
            ['type', 'data', 'bounds', 'quality', 'count'])

    def _examplefunc(self):
        #s = str( randint(0,100))
        #self.labell.text = s
        self._send_request_dzyk(
            'bal_sum/', params=None,
            success=self._get_commands_result_dzyk_balance_allsum, error=self._get_commands_error_dzyk)


    def __init__(self, **kwargs):
        super(ZbarQrcodeDetector, self).__init__(**kwargs)
        # my code
        #
        self.add_widget(self.labell)


        def Course_thread(dt):
            self.labell.text = "24923849"
            self._examplefunc()
            print "r"
            #self.examplefunc("rrrr")

            #self._send_request_dzyk(
            #    'bal_sum/', params=None,
            #    success=self._get_commands_result_dzyk_balance_allsum, error=self._get_commands_error_dzyk)


        Clock.schedule_interval(Course_thread, 1)


        # ID of the command being executed
        self._cmd_id = None

        # List of the "completed" statuses.
        # The first status should be "Done"
        self._completed = []

        # If True - sends a request to retrieve a command status
        self._wait_completion = False

        # requested command
        self._command = (0, '')


        #----------------------------------
        self._camera = AndroidCamera(
                size=self.camera_size,
                size_hint=(None, None))
        self._camera.bind(on_preview_frame=self._detect_qrcode_frame)
        self.add_widget(self._camera)

        # create a scanner used for detecting qrcode
        self._scanner = ImageScanner()
        self._scanner.setConfig(0, Config.ENABLE, 0)
        self._scanner.setConfig(Symbol.QRCODE, Config.ENABLE, 1)
        self._scanner.setConfig(0, Config.X_DENSITY, 3)
        self._scanner.setConfig(0, Config.Y_DENSITY, 3)

    def start(self):
        self._camera.start()

    def stop(self):
        self._camera.stop()

    def _detect_qrcode_frame(self, instance, camera, data):
        # the image we got by default from a camera is using the NV21 format
        # zbar only allow Y800/GREY image, so we first need to convert,
        # then start the detection on the image
        parameters = camera.getParameters()
        size = parameters.getPreviewSize()
        barcode = Image(size.width, size.height, 'NV21')
        barcode.setData(data)
        barcode = barcode.convert('Y800')

        result = self._scanner.scanImage(barcode)

        if result == 0:
            self.symbols = []
            return

        # we detected qrcode! extract and dispatch them
        symbols = []
        it = barcode.getSymbols().iterator()
        while it.hasNext():
            symbol = it.next()
            qrcode = ZbarQrcodeDetector.Qrcode(
                type=symbol.getType(),
                data=symbol.getData(),
                quality=symbol.getQuality(),
                count=symbol.getCount(),
                bounds=symbol.getBounds())
            symbols.append(qrcode)
            self.dataqr = symbol.getData()


        self.symbols = symbols


    '''
    # can't work, due to the overlay.
    def on_symbols(self, instance, value):
        if self.show_bounds:
            self.update_bounds()

    def update_bounds(self):
        self.canvas.after.remove_group('bounds')
        if not self.symbols:
            return
        with self.canvas.after:
            Color(1, 0, 0, group='bounds')
            for symbol in self.symbols:
                x, y, w, h = symbol.bounds
                x = self._camera.right - x - w
                y = self._camera.top - y - h
                Line(rectangle=[x, y, w, h], group='bounds')
    '''


if __name__ == '__main__':

    qrcode_kv = '''
BoxLayout:
    orientation: 'vertical'

    ZbarQrcodeDetector:
        id: detector

    Label:
        text: '\\n'.join(map(repr, detector.symbols))
        size_hint_y: None
        height: '100dp'

    Label:
        id: labell
        text: "labell"
        size_hint_y: None
        height: '100dp'

    TextInput:
        id: addfriendinput
        text: repr(detector.dataqr)


    BoxLayout:
        size_hint_y: None
        height: '48dp'

        Button:
            text: 'Scan a qrcode'
            on_release: detector.start()
        Button:
            text: 'Stop detection'
            on_release: detector.stop()
'''

    class QrcodeExample(App):
        def build(self):
            return Builder.load_string(qrcode_kv)

    QrcodeExample().run()
