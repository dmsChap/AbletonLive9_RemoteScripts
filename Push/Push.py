#Embedded file name: /Users/versonator/Jenkins/live/Projects/AppLive/Resources/MIDI Remote Scripts/Push/Push.py
from __future__ import with_statement
import Live
from contextlib import contextmanager
from functools import partial
from _Framework.Dependency import inject
from _Framework.ButtonElement import ButtonElement
from _Framework.ControlSurface import ControlSurface
from _Framework.ControlElement import OptimizedOwnershipHandler
from _Framework.InputControlElement import MIDI_CC_TYPE, MIDI_NOTE_TYPE
from _Framework.ButtonMatrixElement import ButtonMatrixElement
from _Framework.ModesComponent import AddLayerMode, MultiEntryMode, ModesComponent, SetAttributeMode, CancellableBehaviour, AlternativeBehaviour, ReenterBehaviour, DynamicBehaviourMixin, ExcludingBehaviourMixin, EnablingModesComponent
from _Framework.SysexValueControl import SysexValueControl
from _Framework.Layer import Layer
from _Framework.Resource import PrioritizedResource
from _Framework.DeviceBankRegistry import DeviceBankRegistry
from _Framework.SubjectSlot import subject_slot, subject_slot_group
from _Framework.Util import find_if, clamp, nop, mixin, const, recursive_map, NamedTuple, get_slice
from _Framework.Defaults import TIMER_DELAY
from OptionalElement import OptionalElement, ChoosingElement
from ComboElement import ComboElement, DoublePressElement, MultiElement, DoublePressContext
from HandshakeComponent import HandshakeComponent, make_dongle_message
from ValueComponent import ValueComponent, ParameterValueComponent
from ConfigurableButtonElement import ConfigurableButtonElement, PadButtonElement
from SpecialSessionComponent import SpecialSessionComponent, SpecialSessionZoomingComponent
from SpecialMixerComponent import SpecialMixerComponent
from SpecialTransportComponent import SpecialTransportComponent
from SpecialPhysicalDisplay import SpecialPhysicalDisplay
from MelodicComponent import MelodicComponent
from StepSeqComponent import StepSeqComponent, DrumGroupFinderComponent
from NoteSettingsComponent import NoteEditorSettingsComponent
from GridResolution import GridResolution
from LoopSelectorComponent import LoopSelectorComponent
from ViewControlComponent import ViewControlComponent
from ClipControlComponent import ClipControlComponent
from ProviderDeviceComponent import ProviderDeviceComponent
from DeviceNavigationComponent import DeviceNavigationComponent
from SessionRecordingComponent import SessionRecordingComponent
from SelectedTrackParameterProvider import SelectedTrackParameterProvider
from NoteRepeatComponent import NoteRepeatComponent
from ClipCreator import ClipCreator
from MatrixMaps import PAD_TRANSLATIONS, FEEDBACK_CHANNELS
from BackgroundComponent import BackgroundComponent, ModifierBackgroundComponent
from BrowserComponent import BrowserComponent
from BrowserModes import BrowserHotswapMode
from Actions import CreateInstrumentTrackComponent, CreateDefaultTrackComponent, CaptureAndInsertSceneComponent, DuplicateDetailClipComponent, DuplicateLoopComponent, SelectComponent, DeleteComponent, DeleteSelectedClipComponent, DeleteSelectedSceneComponent, CreateDeviceComponent
from M4LInterfaceComponent import M4LInterfaceComponent
from UserSettingsComponent import UserComponent
from MessageBoxComponent import DialogComponent, NotificationComponent, InfoComponent, align_right
from TouchEncoderElement import TouchEncoderElement
from TouchStripElement import TouchStripElement
from TouchStripController import TouchStripControllerComponent, TouchStripEncoderConnection
from TrackFrozenMode import TrackFrozenModesComponent
from Selection import L9CSelection
from AccentComponent import AccentComponent
from AutoArmComponent import AutoArmComponent
from QuantizationComponent import QuantizationComponent
from WithPriority import WithPriority, Resetting
from Settings import make_pad_parameters, SETTING_WORKFLOW, SETTING_THRESHOLD, SETTING_CURVE
from PadSensitivity import PadUpdateComponent, pad_parameter_sender
from PlayheadElement import PlayheadElement, NullPlayhead
from DeviceParameterComponent import DeviceParameterComponent
from SelectPlayingClipComponent import SelectPlayingClipComponent
import Skin
import consts
import Colors
import Sysex
import Settings
GLOBAL_MAP_MODE = Live.MidiMap.MapMode.relative_smooth_two_compliment

class Push(ControlSurface):
    """
    Push controller script.
    
    Disclaimer: Any use of the Push control surface code (the "Code")
    or parts thereof for commercial purposes or in a commercial context
    is not allowed. Though we do not grant a license for non-commercial
    use of the Code, you may use it in this regard but should be aware that
    (1) we reserve the right to deny the future use any time and
    (2) you need to check whether the use is allowed under the national law
    applicable to your use.
    """

    def __init__(self, c_instance):
        super(Push, self).__init__(c_instance)
        self._optimized_ownership_handler = OptimizedOwnershipHandler()
        self._double_press_context = DoublePressContext()
        injecting = inject(double_press_context=const(self._double_press_context), element_ownership_handler=const(self._optimized_ownership_handler), expect_dialog=const(self.expect_dialog), show_notification=const(self.show_notification), selection=lambda : L9CSelection(application=self.application(), device_component=self._device_parameter_provider, navigation_component=self._device_navigation))
        self._push_injector = injecting.everywhere()
        with self.component_guard():
            self._suppress_sysex = False
            self._skin = Skin.make_default_skin()
            self._clip_creator = ClipCreator()
            self._device_selection_follows_track_selection = True
            self._note_editor_settings = []
            self._create_pad_sensitivity_update()
            self._create_controls()
            self._init_settings()
            self._init_message_box()
            self._init_background()
            self._init_user()
            self._init_touch_strip_controller()
            self._init_accent()
            self._init_transport_and_recording()
            self._init_track_frozen()
            self._init_duplicate_actions()
            self._init_delete_actions()
            self._init_quantize_actions()
            self._init_value_components()
            self._init_mixer()
            self._init_track_mixer()
            self._init_session()
            self._init_grid_resolution()
            self._init_step_sequencer()
            self._init_instrument()
            self._init_scales()
            self._init_note_repeat()
            self._init_matrix_modes()
            self._init_track_modes()
            self._init_device()
            self._init_browser()
            self._init_clip_settings()
            self._init_main_modes()
            self._init_m4l_interface()
            self._init_handshake()
            self.set_pad_translations(PAD_TRANSLATIONS)
            self._on_selected_track_changed()
            self._on_session_record_changed.subject = self.song()
            self._on_session_record_changed()
            self._on_selected_track_is_frozen_changed.subject = self.song().view
            self.set_highlighting_session_component(self._session)
            self.set_feedback_channels(FEEDBACK_CHANNELS)
        self.log_message('Push script loaded')
        self._send_midi(Sysex.WELCOME_MESSAGE)

    def disconnect(self):
        self._pre_serialize()
        with self.component_guard():
            self._user.mode = Sysex.USER_MODE
        super(Push, self).disconnect()
        self._send_midi(Sysex.GOOD_BYE_MESSAGE)
        self.log_message('Push script unloaded')

    @contextmanager
    def component_guard(self):
        with super(Push, self).component_guard():
            with self._push_injector:
                song_view = self.song().view
                old_selected_track = song_view.selected_track
                yield
                if song_view.selected_track != old_selected_track:
                    self._track_selection_changed_by_action()
                self._optimized_ownership_handler.commit_ownership_changes()

    def _track_selection_changed_by_action(self):
        if self._matrix_modes.selected_mode == 'note':
            self._session_recording.deactivate_recording()
        if self._auto_arm.needs_restore_auto_arm:
            self._auto_arm.restore_auto_arm()

    def refresh_state(self):
        super(Push, self).refresh_state()
        if self._user.mode == Sysex.LIVE_MODE:
            self.schedule_message(5, self._start_handshake)

    def _pre_serialize(self):
        """
        This will pre-serialize all settings, as a later access to
        Push's objects might cause problems with Pickle
        """
        from pickle import dumps
        from encodings import ascii
        nop(ascii)
        preferences = self._c_instance.preferences('Push')
        dump = dumps(self._pref_dict)
        preferences.set_serializer(lambda : dump)

    def _init_settings(self):
        from pickle import loads, dumps
        from encodings import ascii
        nop(ascii)
        preferences = self._c_instance.preferences('Push')
        self._pref_dict = {}
        try:
            self._pref_dict = loads(str(preferences))
        except Exception:
            pass

        pref_dict = self._pref_dict
        preferences.set_serializer(lambda : dumps(pref_dict))
        self._settings = Settings.create_settings(preferences=self._pref_dict)
        self._on_pad_curve.subject = self._settings[SETTING_CURVE]
        self._on_pad_threshold.subject = self._settings[SETTING_THRESHOLD]

    def _init_handshake(self):
        dongle_message, dongle = make_dongle_message(Sysex.DONGLE_ENQUIRY_PREFIX)
        identity_control = SysexValueControl(Sysex.IDENTITY_PREFIX, Sysex.IDENTITY_ENQUIRY)
        dongle_control = SysexValueControl(Sysex.DONGLE_PREFIX, dongle_message)
        presentation_control = SysexValueControl(Sysex.DONGLE_PREFIX, Sysex.make_presentation_message(self.application()))
        self._handshake = HandshakeComponent(identity_control=identity_control, dongle_control=dongle_control, presentation_control=presentation_control, dongle=dongle)
        self._on_handshake_success.subject = self._handshake
        self._on_handshake_failure.subject = self._handshake

    def _start_handshake(self):
        self._playhead_element.proxied_object = self._c_instance.playhead
        self._note_repeat.set_note_repeat(self._c_instance.note_repeat)
        self._accent_component.set_full_velocity(self._c_instance.full_velocity)
        for control in self.controls:
            receive_value_backup = getattr(control, '_receive_value_backup', nop)
            if receive_value_backup != nop:
                control.receive_value = receive_value_backup
            send_midi_backup = getattr(control, '_send_midi_backup', nop)
            if send_midi_backup != nop:
                control.send_midi = send_midi_backup

        self._handshake._start_handshake()
        self.update()

    def update(self):
        self._on_session_record_changed()
        self.reset_controlled_track()
        self.set_feedback_channels(FEEDBACK_CHANNELS)
        self._update_calibration()
        super(Push, self).update()

    @subject_slot('success')
    def _on_handshake_success(self):
        self.log_message('Handshake succeded with firmware version %.2f!' % self._handshake.firmware_version)
        self.update()
        self._c_instance.set_firmware_version(self._handshake.firmware_version)

    @subject_slot('failure')
    def _on_handshake_failure(self, bootloader_mode):
        self.log_message('Handshake failed, performing harakiri!')
        if bootloader_mode:
            self._c_instance.set_firmware_version(0.0)
        self._c_instance.playhead.enabled = False
        self._playhead_element.proxied_object = NullPlayhead()
        self._note_repeat.set_note_repeat(None)
        self._accent_component.set_full_velocity(None)
        for control in self.controls:
            receive_value_backup = getattr(control, 'receive_value', nop)
            send_midi_backup = getattr(control, 'send_midi', nop)
            try:
                control.receive_value = nop
                if receive_value_backup != nop:
                    control._receive_value_backup = receive_value_backup
                control.send_midi = nop
                if send_midi_backup != nop:
                    control._send_midi_backup = send_midi_backup
            except AttributeError:
                pass

    def _update_calibration(self):
        self._send_midi(Sysex.CALIBRATION_SET)

    def _create_pad_sensitivity_update(self):
        all_pad_sysex_control = SysexValueControl(Sysex.ALL_PADS_SENSITIVITY_PREFIX)
        pad_sysex_control = SysexValueControl(Sysex.PAD_SENSITIVITY_PREFIX)
        sensitivity_sender = pad_parameter_sender(all_pad_sysex_control, pad_sysex_control)
        self._pad_sensitivity_update = PadUpdateComponent(all_pads=range(64), parameter_sender=sensitivity_sender, default_profile=Settings.action_pad_sensitivity, update_delay=TIMER_DELAY)

    def _create_controls(self):
        is_momentary = True

        def create_button(note, name, **k):
            button = ConfigurableButtonElement(is_momentary, MIDI_CC_TYPE, 0, note, name=name, skin=self._skin, **k)
            return button

        def create_modifier_button(note, name, **k):
            button = create_button(note, name, resource_type=PrioritizedResource, **k)
            return button

        undo_handler = self.song()
        self._foot_pedal_button = DoublePressElement(create_button(69, 'Foot_Pedal'))
        self._nav_up_button = create_button(46, 'Up_Arrow')
        self._nav_down_button = create_button(47, 'Down_Arrow')
        self._nav_left_button = create_button(44, 'Left_Arrow')
        self._nav_right_button = create_button(45, 'Right_Arrow')
        self._nav_up_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._nav_down_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._nav_left_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._nav_right_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._shift_button = create_modifier_button(49, 'Shift_Button')
        self._select_button = create_modifier_button(48, 'Select_Button')
        self._delete_button = create_modifier_button(118, 'Delete_Button', undo_step_handler=undo_handler)
        self._duplicate_button = create_modifier_button(88, 'Duplicate_Button', undo_step_handler=undo_handler)
        self._quantize_button = create_modifier_button(116, 'Quantization_Button', undo_step_handler=undo_handler)
        self._accent_button = create_modifier_button(57, 'Accent_Button')
        self._in_button = create_button(62, 'In_Button')
        self._out_button = create_button(63, 'Out_Button')
        self._master_select_button = create_button(28, 'Master_Select_Button')
        self._octave_down_button = create_button(54, 'Octave_Down_Button')
        self._octave_up_button = create_button(55, 'Octave_Up_Button')
        self._repeat_button = create_button(56, 'Repeat_Button')
        self._octave_up_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._octave_down_button.default_states = consts.SCROLL_SIDE_BUTTON_STATES
        self._global_mute_button = create_modifier_button(60, 'Global_Mute_Button')
        self._global_solo_button = create_modifier_button(61, 'Global_Solo_Button')
        self._global_track_stop_button = create_modifier_button(29, 'Track_Stop_Button')
        self._scale_presets_button = create_button(58, 'Scale_Presets_Button')
        self._vol_mix_mode_button = create_button(114, 'Vol_Mix_Mode_Button')
        self._device_mode_button = create_button(110, 'Device_Mode_Button')
        self._clip_mode_button = create_button(113, 'Clip_Mode_Button')
        self._browse_mode_button = create_button(111, 'Browse_Mode_Button')
        self._single_track_mix_mode_button = create_button(112, 'Single_Track_Mode_Button')
        self._pan_send_mix_mode_button = create_button(115, 'Pan_Send_Mode_Button', resource_type=PrioritizedResource)
        self._note_mode_button = create_button(50, 'Note_Mode_Button')
        self._session_mode_button = create_button(51, 'Session_Mode_Button')
        self._play_button = create_button(85, 'Play_Button')
        self._new_button = create_button(87, 'New_Button')
        self._automation_button = create_button(89, 'Automation_Button')
        self._tap_tempo_button = create_button(3, 'Tap_Tempo_Button')
        self._metronome_button = create_button(9, 'Metronome_Button')
        self._fixed_length_button = create_button(90, 'Fixed_Length_Button')
        self._record_button = create_button(86, 'Record_Button')
        self._undo_button = create_button(119, 'Undo_Button')
        self._create_device_button = create_button(52, 'Create_Device_Button', undo_step_handler=undo_handler)
        self._create_track_button = create_button(53, 'Create_Track_Button', undo_step_handler=undo_handler)
        self._double_button = create_button(117, 'Double_Button', undo_step_handler=undo_handler)
        self._user_button = create_button(59, 'User_Button', undo_step_handler=undo_handler)
        self._select_buttons = ButtonMatrixElement(name='Track_Select_Buttons', rows=[[ create_button(20 + idx, 'Track_Select_Button' + str(idx)) for idx in xrange(8) ]])
        self._track_state_buttons = ButtonMatrixElement(name='Track_State_Buttons', rows=[[ create_button(102 + idx, 'Track_State_Button' + str(idx), is_rgb=True) for idx in xrange(8) ]])
        self._side_buttons = ButtonMatrixElement(name='Scene_Launch_Buttons', rows=[[ create_button(36 + idx, 'Scene_Launch_Button' + str(idx), default_states={True: 'Session.SceneSelected',
          False: 'Session.SceneUnselected'}) for idx in reversed(xrange(8)) ]])

        def create_display_line(clear_cmd, write_cmd, index):
            line = SpecialPhysicalDisplay(consts.DISPLAY_LENGTH, 1)
            line.set_clear_all_message(clear_cmd)
            line.set_message_parts(write_cmd, (247,))
            line.name = 'Display_Line_%d' % index
            line.reset()
            return line

        self._display_line1 = create_display_line(Sysex.CLEAR_LINE1, Sysex.WRITE_LINE1, 0)
        self._display_line2 = create_display_line(Sysex.CLEAR_LINE2, Sysex.WRITE_LINE2, 1)
        self._display_line3 = create_display_line(Sysex.CLEAR_LINE3, Sysex.WRITE_LINE3, 2)
        self._display_line4 = create_display_line(Sysex.CLEAR_LINE4, Sysex.WRITE_LINE4, 3)
        self._display_lines = [self._display_line1,
         self._display_line2,
         self._display_line3,
         self._display_line4]

        def create_pad_button(pad_id, name, **k):
            return PadButtonElement(pad_id, self._pad_sensitivity_update, is_momentary, MIDI_NOTE_TYPE, 0, (36 + pad_id), skin=self._skin, name=name, **k)

        matrix_rows = [ [ create_pad_button((7 - row) * 8 + column, str(column) + '_Clip_' + str(row) + '_Button', is_rgb=True, default_states={True: 'DefaultMatrix.On',
         False: 'DefaultMatrix.Off'}) for column in xrange(8) ] for row in xrange(8) ]
        double_press_rows = recursive_map(DoublePressElement, matrix_rows)
        self._matrix = ButtonMatrixElement(name='Button_Matrix', rows=matrix_rows)
        self._double_press_matrix = ButtonMatrixElement(name='Double_Press_Matrix', rows=double_press_rows)
        self._single_press_event_matrix = ButtonMatrixElement(name='Single_Press_Event_Matrix', rows=recursive_map(lambda x: x.single_press, double_press_rows))
        self._double_press_event_matrix = ButtonMatrixElement(name='Double_Press_Event_Matrix', rows=recursive_map(lambda x: x.double_press, double_press_rows))

        def create_note_button(note, name, **k):
            return ConfigurableButtonElement(is_momentary, MIDI_NOTE_TYPE, 0, note, skin=self._skin, name=name, **k)

        self._touch_strip_tap = create_note_button(12, 'Touch_Strip_Tap')
        self._touch_strip_control = TouchStripElement(name='Touch_Strip_Control', touch_button=self._touch_strip_tap)
        self._touch_strip_control.set_feedback_delay(-1)
        self._touch_strip_control.set_needs_takeover(False)

        class Deleter(object):

            @property
            def is_deleting(_):
                return self._delete_component.is_deleting

            def delete_clip_envelope(_, param):
                return self._delete_component.delete_clip_envelope(param)

        deleter = Deleter()
        self._tempo_control_tap = create_note_button(10, 'Tempo_Control_Tap')
        self._tempo_control = TouchEncoderElement(MIDI_CC_TYPE, 0, 14, GLOBAL_MAP_MODE, name='Tempo_Control', undo_step_handler=self.song(), delete_handler=deleter, encoder_sensitivity=consts.ENCODER_SENSITIVITY, touch_button=self._tempo_control_tap)
        self._swing_control_tap = create_note_button(9, 'Swing_Control_Tap')
        self._swing_control = TouchEncoderElement(MIDI_CC_TYPE, 0, 15, GLOBAL_MAP_MODE, name='Swing_Control', undo_step_handler=self.song(), delete_handler=deleter, encoder_sensitivity=consts.ENCODER_SENSITIVITY, touch_button=self._swing_control_tap)
        self._master_volume_control_tap = create_note_button(8, 'Master_Volume_Tap')
        self._master_volume_control = TouchEncoderElement(MIDI_CC_TYPE, 0, 79, GLOBAL_MAP_MODE, undo_step_handler=self.song(), delete_handler=deleter, name='Master_Volume_Control', encoder_sensitivity=consts.ENCODER_SENSITIVITY, touch_button=self._master_volume_control_tap)
        self._global_param_touch_buttons_raw = [ create_note_button(index, 'Track_Control_Touch_' + str(index)) for index in range(8) ]
        self._global_param_touch_buttons = ButtonMatrixElement(name='Track_Control_Touches', rows=[self._global_param_touch_buttons_raw])
        self._global_param_controls = ButtonMatrixElement(name='Track_Controls', rows=[[ TouchEncoderElement(MIDI_CC_TYPE, 0, 71 + index, GLOBAL_MAP_MODE, undo_step_handler=self.song(), delete_handler=deleter, encoder_sensitivity=consts.ENCODER_SENSITIVITY, name='Track_Control_' + str(index), touch_button=self._global_param_touch_buttons_raw[index]) for index in xrange(8) ]])
        self._on_param_encoder_touched.replace_subjects(self._global_param_touch_buttons_raw)
        self._aftertouch_control = SysexValueControl(Sysex.SET_AFTERTOUCH_MODE, default_value=Sysex.POLY_AFTERTOUCH)
        self._any_touch_button = MultiElement(*self._global_param_touch_buttons.nested_control_elements())
        self._playhead_element = PlayheadElement(self._c_instance.playhead)

    def _init_background(self):
        self._background = BackgroundComponent()
        self._background.layer = Layer(display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, top_buttons=self._select_buttons, bottom_buttons=self._track_state_buttons, scales_button=self._scale_presets_button, octave_up=self._octave_up_button, octave_down=self._octave_down_button, side_buttons=self._side_buttons, repeat_button=self._repeat_button, accent_button=self._accent_button, double_button=self._double_button, in_button=self._in_button, out_button=self._out_button, param_controls=self._global_param_controls, param_touch=self._global_param_touch_buttons, tempo_control_tap=self._tempo_control_tap, master_control_tap=self._master_volume_control_tap, touch_strip=self._touch_strip_control, touch_strip_tap=self._touch_strip_tap, nav_up_button=self._nav_up_button, nav_down_button=self._nav_down_button, nav_left_button=self._nav_left_button, nav_right_button=self._nav_right_button, aftertouch=self._aftertouch_control, _notification=self._notification.use_single_line(2))
        self._background.layer.priority = consts.BACKGROUND_PRIORITY
        self._matrix_background = BackgroundComponent()
        self._matrix_background.set_enabled(False)
        self._matrix_background.layer = Layer(matrix=self._matrix)
        self._mod_background = ModifierBackgroundComponent()
        self._mod_background.layer = Layer(shift_button=self._shift_button, select_button=self._select_button, delete_button=self._delete_button, duplicate_button=self._duplicate_button, quantize_button=self._quantize_button)

    def _can_auto_arm_track(self, track):
        routing = track.current_input_routing
        return routing == 'Ext: All Ins' or routing == 'All Ins' or routing.startswith('Push Input')

    def _init_touch_strip_controller(self):
        strip_controller = TouchStripControllerComponent()
        strip_controller.set_enabled(False)
        strip_controller.layer = Layer(touch_strip=self._touch_strip_control)
        strip_controller.layer.priority = consts.MODAL_DIALOG_PRIORITY
        self._strip_connection = TouchStripEncoderConnection(strip_controller, self._touch_strip_tap)
        self._tempo_control.set_observer(self._strip_connection)
        self._swing_control.set_observer(self._strip_connection)
        self._master_volume_control.set_observer(self._strip_connection)
        for encoder in self._global_param_controls.nested_control_elements():
            encoder.set_observer(self._strip_connection)

    def _init_matrix_modes(self):
        self._auto_arm = AutoArmComponent(name='Auto_Arm')
        self._auto_arm.can_auto_arm_track = self._can_auto_arm_track
        self._auto_arm.notification_layer = Layer(display_line1=self._display_line3)
        self._auto_arm.notification_layer.priority = consts.NOTIFICATION_PRIORITY
        self._select_playing_clip = SelectPlayingClipComponent(name='Select_Playing_Clip', playing_clip_above_layer=Layer(action_button=self._nav_up_button), playing_clip_below_layer=Layer(action_button=self._nav_down_button))
        self._select_playing_clip.notification_layer = Layer(display_line1=self._display_line3)
        self._select_playing_clip.notification_layer.priority = consts.NOTIFICATION_PRIORITY
        self._drum_group_finder = DrumGroupFinderComponent()
        self._on_drum_group_changed.subject = self._drum_group_finder
        self._note_modes = ModesComponent(name='Note_Modes')
        self._note_modes.add_mode('sequencer', [self._note_repeat_enabler, self._accent_component, self._step_sequencer])
        self._note_modes.add_mode('looper', self._audio_loop if consts.PROTO_AUDIO_NOTE_MODE else self._matrix_background)
        self._note_modes.add_mode('instrument', [self._note_repeat_enabler, self._accent_component, self._instrument])
        self._note_modes.add_mode('disabled', self._matrix_background)
        self._note_modes.selected_mode = 'disabled'
        self._note_modes.set_enabled(False)

        def switch_note_mode_layout():
            if self._note_modes.selected_mode == 'instrument':
                getattr(self._instrument, 'cycle_mode', nop)()

        self._matrix_modes = ModesComponent(name='Matrix_Modes')
        self._matrix_modes.add_mode('session', [(self._zooming, self._zooming_layer), (self._session, self._session_layer), AddLayerMode(self._session, self._restricted_session_layer)])
        self._matrix_modes.add_mode('note', [self._drum_group_finder,
         self._view_control,
         self._note_modes,
         self._delete_clip,
         self._select_playing_clip,
         (self._session, self._restricted_session_layer)], behaviour=self._auto_arm.auto_arm_restore_behaviour(ReenterBehaviour, on_reenter=switch_note_mode_layout))
        self._matrix_modes.selected_mode = 'note'
        self._matrix_modes.layer = Layer(session_button=self._session_mode_button, note_button=self._note_mode_button)
        self._on_matrix_mode_changed.subject = self._matrix_modes
        self._matrix_modes.selected_mode = 'note'

    def _init_accent(self):
        self._accent_component = AccentComponent()
        self._accent_component.set_full_velocity(self._c_instance.full_velocity)
        self._accent_component.set_enabled(False)
        self._accent_component.layer = Layer(toggle_button=self._accent_button)
        self._on_accent_mode_changed.subject = self._accent_component

    def _init_user(self):
        sysex_control = SysexValueControl(Sysex.MODE_CHANGE)
        self._user = UserComponent(value_control=sysex_control)
        self._user.layer = Layer(action_button=self._user_button)
        self._user.settings_layer = Layer(display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, encoders=self._global_param_controls)
        self._user.settings_layer.priority = consts.DIALOG_PRIORITY
        self._user.settings = self._settings
        self._on_hardware_mode_changed.subject = self._user
        self._on_before_hardware_mode_sent.subject = self._user
        self._on_after_hardware_mode_sent.subject = self._user
        self._update_pad_params()

    def _init_session(self):
        self._session = SpecialSessionComponent(8, 8, name='Session_Control')
        self._session.set_mixer(self._mixer)
        for scene_index in xrange(8):
            scene = self._session.scene(scene_index)
            scene.set_triggered_value(self._skin['Session.SceneTriggered'])
            scene.name = 'Scene_' + str(scene_index)
            scene.layer = Layer(select_button=self._select_button, delete_button=self._delete_button)
            scene._do_select_scene = self._selector.on_select_scene
            for track_index in xrange(8):
                clip_slot = scene.clip_slot(track_index)
                clip_slot.name = str(track_index) + '_Clip_Slot_' + str(scene_index)
                clip_slot.set_triggered_to_play_value('Session.ClipTriggeredPlay')
                clip_slot.set_triggered_to_record_value('Session.ClipTriggeredRecord')
                clip_slot.set_clip_palette(Colors.CLIP_COLOR_TABLE)
                clip_slot.set_clip_rgb_table(Colors.RGB_COLOR_TABLE)
                clip_slot.set_record_button_value('Session.RecordButton')
                clip_slot.set_started_value('Session.ClipStarted')
                clip_slot.set_recording_value('Session.ClipRecording')
                clip_slot._do_select_clip = self._selector.on_select_clip
                clip_slot.layer = Layer(delete_button=self._delete_button, select_button=self._select_button, duplicate_button=self._duplicate_button)

        self._session_layer = Layer(page_up_button=self._octave_up_button, page_down_button=self._octave_down_button, track_bank_left_button=self._nav_left_button, track_bank_right_button=self._nav_right_button, scene_bank_up_button=self._nav_up_button, scene_bank_down_button=self._nav_down_button, clip_launch_buttons=self._matrix, scene_launch_buttons=self._side_buttons, duplicate_button=self._duplicate_button)
        self._restricted_session_layer = Layer(stop_all_clips_button=ComboElement(self._global_track_stop_button, [self._shift_button]))
        self._session_stop_track_layer = Layer(stop_track_clip_buttons=self._track_state_buttons)
        self._session.duplicate_layer = Layer(scene_buttons=self._side_buttons)
        self._zooming = SpecialSessionZoomingComponent(self._session, name='Session_Overview')
        self._zooming.set_enabled(False)
        self._zooming.set_stopped_value(self._skin['Zooming.Stopped'])
        self._zooming.set_selected_value(self._skin['Zooming.Selected'])
        self._zooming.set_playing_value(self._skin['Zooming.Playing'])
        self._zooming.set_empty_value(self._skin['Zooming.Empty'])
        self._zooming_layer = Layer(button_matrix=self._matrix, zoom_button=self._shift_button, nav_up_button=self._nav_up_button, nav_down_button=self._nav_down_button, nav_left_button=self._nav_left_button, nav_right_button=self._nav_right_button)
        self._session.set_enabled(True)
        self._zooming.set_enabled(True)

    def _init_track_modes(self):
        self._track_modes = ModesComponent(name='Track_Modes')
        self._track_modes.set_enabled(False)
        self._track_modes.add_mode('stop', AddLayerMode(self._session, self._session_stop_track_layer))
        self._track_modes.add_mode('solo', AddLayerMode(self._mixer, self._mixer_solo_layer))
        self._track_modes.add_mode('mute', AddLayerMode(self._mixer, self._mixer_mute_layer))
        self._track_modes.layer = Layer(stop_button=self._global_track_stop_button, mute_button=self._global_mute_button, solo_button=self._global_solo_button, shift_button=self._shift_button)
        self._track_modes.selected_mode = 'mute'

    def _init_main_modes(self):

        def configure_note_editor_settings(parameter_provider, mode):
            for note_editor_setting in self._note_editor_settings:
                note_editor_setting.component.parameter_provider = parameter_provider
                note_editor_setting.component.automation_layer = getattr(note_editor_setting, mode + '_automation_layer')

        def when_track_is_not_frozen(*modes):
            return TrackFrozenModesComponent(default_mode=[modes], frozen_mode=self._track_frozen_info, is_enabled=False)

        track_note_editor_mode = partial(configure_note_editor_settings, self._track_parameter_provider, 'track')
        device_note_editor_mode = partial(configure_note_editor_settings, self._device_parameter_provider, 'device')
        enable_stop_mute_solo_as_modifiers = AddLayerMode(self._mod_background, Layer(stop=self._global_track_stop_button, mute=self._global_mute_button, solo=self._global_solo_button))
        self._main_modes = ModesComponent()
        self._main_modes.add_mode('volumes', [self._track_modes, (self._mixer, self._mixer_volume_layer), track_note_editor_mode])
        self._main_modes.add_mode('pan_sends', [self._track_modes, (self._mixer, self._mixer_pan_send_layer), track_note_editor_mode])
        self._main_modes.add_mode('track', [self._track_modes,
         self._track_mixer,
         (self._mixer, self._mixer_track_layer),
         track_note_editor_mode])
        self._main_modes.add_mode('clip', [self._track_modes, (self._mixer, self._mixer_layer), when_track_is_not_frozen(partial(self._view_control.show_view, 'Detail/Clip'), self._clip_control)])
        self._main_modes.add_mode('device', [when_track_is_not_frozen(enable_stop_mute_solo_as_modifiers, partial(self._view_control.show_view, 'Detail/DeviceChain'), self._device_parameter_component, self._device_navigation, device_note_editor_mode)], behaviour=ReenterBehaviour(self._device_navigation.back_to_top))
        self._main_modes.add_mode('browse', [when_track_is_not_frozen(enable_stop_mute_solo_as_modifiers, partial(self._view_control.show_view, 'Browser'), self._browser.back_to_top, self._browser_hotswap_mode, self._browser_mode, self._browser.reset_load_memory)], groups=['add_effect', 'add_track', 'browse'], behaviour=mixin(DynamicBehaviourMixin, CancellableBehaviour)(lambda : not self._browser_hotswap_mode._mode.can_hotswap() and 'add_effect_left'))
        self._main_modes.add_mode('add_effect_right', [when_track_is_not_frozen(enable_stop_mute_solo_as_modifiers, self._browser.back_to_top, self._create_device_right)], behaviour=mixin(ExcludingBehaviourMixin, CancellableBehaviour)(['add_track', 'browse']), groups=['add_effect'])
        self._main_modes.add_mode('add_effect_left', [when_track_is_not_frozen(enable_stop_mute_solo_as_modifiers, self._browser.back_to_top, self._create_device_left)], behaviour=mixin(ExcludingBehaviourMixin, CancellableBehaviour)(['add_track', 'browse']), groups=['add_effect'])
        self._main_modes.add_mode('add_instrument_track', [enable_stop_mute_solo_as_modifiers, self._browser.back_to_top, self._create_instrument_track], behaviour=mixin(ExcludingBehaviourMixin, AlternativeBehaviour)(excluded_groups=['browse', 'add_effect'], alternative_mode='add_default_track'), groups=['add_track'])
        self._main_modes.add_mode('add_default_track', [enable_stop_mute_solo_as_modifiers, self._browser.back_to_top, self._create_default_track], groups=['add_track'])
        self._main_modes.selected_mode = 'device'
        self._main_modes.layer = Layer(volumes_button=self._vol_mix_mode_button, pan_sends_button=self._pan_send_mix_mode_button, track_button=self._single_track_mix_mode_button, clip_button=self._clip_mode_button, device_button=self._device_mode_button, browse_button=self._browse_mode_button, add_effect_right_button=self._create_device_button, add_effect_left_button=ComboElement(self._create_device_button, [self._shift_button]), add_instrument_track_button=self._create_track_button)
        self._on_main_mode_button_value.replace_subjects([self._vol_mix_mode_button,
         self._pan_send_mix_mode_button,
         self._single_track_mix_mode_button,
         self._clip_mode_button,
         self._device_mode_button,
         self._browse_mode_button])

    @subject_slot_group('value')
    def _on_main_mode_button_value(self, value, sender):
        if value:
            self._instrument.scales_menu.selected_mode = 'disabled'

    def _init_track_frozen(self):
        self._track_frozen_info = InfoComponent(info_text=consts.MessageBoxText.TRACK_FROZEN_INFO, is_enabled=False, layer=Layer(display=self._display_line2, _notification=self._notification.use_full_display(1)))

    def _init_mixer(self):
        self._mixer = SpecialMixerComponent(self._matrix.width())
        self._mixer.set_enabled(False)
        self._mixer.name = 'Mixer'
        self._mixer_layer = Layer(track_names_display=self._display_line4, track_select_buttons=self._select_buttons)
        self._mixer_pan_send_layer = Layer(track_names_display=self._display_line4, track_select_buttons=self._select_buttons, pan_send_toggle=self._pan_send_mix_mode_button, pan_send_controls=self._global_param_controls, pan_send_names_display=self._display_line1, pan_send_graphics_display=self._display_line2, selected_track_name_display=self._display_line3, pan_send_values_display=ComboElement(self._display_line3, [self._any_touch_button]))
        self._mixer_volume_layer = Layer(track_names_display=self._display_line4, track_select_buttons=self._select_buttons, volume_controls=self._global_param_controls, volume_names_display=self._display_line1, volume_graphics_display=self._display_line2, selected_track_name_display=self._display_line3, volume_values_display=ComboElement(self._display_line3, [self._any_touch_button]))
        self._mixer_track_layer = Layer(selected_track_name_display=self._display_line3, track_names_display=self._display_line4, track_select_buttons=self._select_buttons)
        self._mixer_solo_layer = Layer(solo_buttons=self._track_state_buttons)
        self._mixer_mute_layer = Layer(mute_buttons=self._track_state_buttons)
        for track in xrange(self._matrix.width()):
            strip = self._mixer.channel_strip(track)
            strip.name = 'Channel_Strip_' + str(track)
            strip.set_invert_mute_feedback(True)
            strip.set_delete_handler(self._delete_component)
            strip._do_select_track = self._selector.on_select_track
            strip.layer = Layer(shift_button=self._shift_button, duplicate_button=self._duplicate_button, selector_button=self._select_button)

        self._mixer.selected_strip().name = 'Selected_Channel_strip'
        self._mixer.master_strip().name = 'Master_Channel_strip'
        self._mixer.master_strip()._do_select_track = self._selector.on_select_track
        self._mixer.master_strip().layer = Layer(volume_control=self._master_volume_control, cue_volume_control=ComboElement(self._master_volume_control, [self._shift_button]), select_button=self._master_select_button, selector_button=self._select_button)
        self._mixer.set_enabled(True)

    def _init_track_mixer(self):
        self._track_parameter_provider = self.register_disconnectable(SelectedTrackParameterProvider())
        self._track_mixer = DeviceParameterComponent(parameter_provider=self._track_parameter_provider, is_enabled=False, layer=Layer(parameter_controls=self._global_param_controls, name_display_line=self._display_line1, graphic_display_line=self._display_line2, value_display_line=ComboElement(self._display_line3, [self._any_touch_button])))

    def _init_device(self):
        self._device_bank_registry = DeviceBankRegistry()
        self._device_parameter_provider = ProviderDeviceComponent(device_bank_registry=self._device_bank_registry, name='DeviceComponent', is_enabled=True)
        self.set_device_component(self._device_parameter_provider)
        self._device_parameter_component = DeviceParameterComponent(parameter_provider=self._device_parameter_provider, is_enabled=False, layer=Layer(parameter_controls=self._global_param_controls, name_display_line=self._display_line1, value_display_line=self._display_line2, graphic_display_line=ComboElement(self._display_line3, [self._any_touch_button])))
        self._device_navigation = DeviceNavigationComponent(device_bank_registry=self._device_bank_registry, is_enabled=False, layer=Layer(enter_button=self._in_button, exit_button=self._out_button, select_buttons=self._select_buttons, state_buttons=self._track_state_buttons, display_line=self._display_line4, _notification=self._notification.use_single_line(2)), info_layer=Layer(display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, _notification=self._notification.use_full_display(2)), delete_handler=self._delete_component)

    def _init_transport_and_recording(self):
        self._view_control = ViewControlComponent(name='View_Control')
        self._view_control.set_enabled(False)
        self._view_control.layer = Layer(prev_track_button=self._nav_left_button, next_track_button=self._nav_right_button, prev_scene_button=OptionalElement(self._nav_up_button, self._settings[SETTING_WORKFLOW], False), next_scene_button=OptionalElement(self._nav_down_button, self._settings[SETTING_WORKFLOW], False), prev_scene_list_button=OptionalElement(self._nav_up_button, self._settings[SETTING_WORKFLOW], True), next_scene_list_button=OptionalElement(self._nav_down_button, self._settings[SETTING_WORKFLOW], True))
        self._session_recording = SessionRecordingComponent(self._clip_creator, self._view_control, name='Session_Recording')
        new_button = MultiElement(self._new_button, self._foot_pedal_button.double_press)
        record_button = MultiElement(self._record_button, self._foot_pedal_button.single_press)
        self._session_recording.layer = Layer(new_button=OptionalElement(new_button, self._settings[SETTING_WORKFLOW], False), scene_list_new_button=OptionalElement(new_button, self._settings[SETTING_WORKFLOW], True), record_button=record_button, automation_button=self._automation_button, new_scene_button=ComboElement(self._new_button, [self._shift_button]), re_enable_automation_button=ComboElement(self._automation_button, [self._shift_button]), delete_automation_button=ComboElement(self._automation_button, [self._delete_button]), length_button=self._fixed_length_button, _uses_foot_pedal=self._foot_pedal_button)
        self._session_recording.length_layer = Layer(display_line=self._display_line4, label_display_line=self._display_line3, blank_display_line2=self._display_line2, blank_display_line1=self._display_line1, select_buttons=self._select_buttons, state_buttons=self._track_state_buttons, _notification=self._notification.use_single_line(1))
        self._session_recording.length_layer.priority = consts.DIALOG_PRIORITY
        self._transport = SpecialTransportComponent(name='Transport')
        self._transport.layer = Layer(shift_button=self._shift_button, play_button=self._play_button, tap_tempo_button=self._tap_tempo_button, metronome_button=self._metronome_button, tempo_encoder=self._tempo_control, undo_button=self._undo_button)

    def _init_clip_settings(self):
        self._clip_control = ClipControlComponent(loop_layer=Layer(encoders=self._global_param_controls.submatrix[:4, :], shift_button=self._shift_button, name_display=self._display_line1.subdisplay[:36], value_display=self._display_line2.subdisplay[:36]), audio_layer=Layer(encoders=self._global_param_controls.submatrix[4:, :], shift_button=self._shift_button, name_display=self._display_line1.subdisplay[36:], value_display=self._display_line2.subdisplay[36:]), clip_name_layer=Layer(display=self._display_line3), name='Clip_Control', is_enabled=False)

    def _init_browser(self):
        self._browser_hotswap_mode = MultiEntryMode(BrowserHotswapMode(application=self.application()))
        self._browser = BrowserComponent(name='Browser')
        self._browser.set_enabled(False)
        self._browser.layer = Layer(encoder_controls=self._global_param_controls, display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, select_buttons=self._select_buttons, state_buttons=self._track_state_buttons, enter_button=self._in_button, exit_button=self._out_button, shift_button=WithPriority(consts.SHARED_PRIORITY, self._shift_button), _notification=self._notification.use_full_display(2))
        self._browser.layer.priority = consts.BROWSER_PRIORITY
        self._browser_mode = MultiEntryMode(self._browser)
        self._browser_dialog_mode = MultiEntryMode([SetAttributeMode(self._browser.layer, 'priority', consts.MODAL_DIALOG_PRIORITY), self._browser_mode])
        self._create_device_right = CreateDeviceComponent(name='Create_Device_Right', browser_component=self._browser, browser_mode=self._browser_dialog_mode, browser_hotswap_mode=self._browser_hotswap_mode, insert_left=False)
        self._create_device_right.set_enabled(False)
        self._create_device_left = CreateDeviceComponent(name='Create_Device_Right', browser_component=self._browser, browser_mode=self._browser_dialog_mode, browser_hotswap_mode=self._browser_hotswap_mode, insert_left=True)
        self._create_device_left.set_enabled(False)
        self._create_default_track = CreateDefaultTrackComponent(name='Create_Default_Track')
        self._create_default_track.options.layer = Layer(display_line=self._display_line4, label_display_line=self._display_line3, blank_display_line2=self._display_line2, blank_display_line1=self._display_line1, select_buttons=self._select_buttons, state_buttons=self._track_state_buttons)
        self._create_default_track.options.layer.priority = consts.MODAL_DIALOG_PRIORITY
        self._create_default_track.set_enabled(False)
        self._create_instrument_track = CreateInstrumentTrackComponent(name='Create_Instrument_Track', browser_component=self._browser, browser_mode=self._browser_dialog_mode, browser_hotswap_mode=self._browser_hotswap_mode)
        self._create_instrument_track.set_enabled(False)
        self._on_browse_mode_changed.subject = self.application().view

    @subject_slot('browse_mode')
    def _on_browse_mode_changed(self):
        if not self.application().browser.hotswap_target:
            if self._main_modes.selected_mode == 'browse' or self._browser_hotswap_mode.is_entered:
                self._main_modes.selected_mode = 'device'

    def _init_grid_resolution(self):
        self._grid_resolution = self.register_disconnectable(GridResolution())

    def _add_note_editor_setting(self):
        note_editor_settings = NoteEditorSettingsComponent(self._grid_resolution, Layer(initial_encoders=self._global_param_controls, priority=consts.MODAL_DIALOG_PRIORITY), Layer(encoders=self._global_param_controls, priority=consts.MODAL_DIALOG_PRIORITY))
        note_editor_settings.settings.layer = Layer(top_display_line=self._display_line1, bottom_display_line=self._display_line2, info_display_line=self._display_line3, clear_display_line=self._display_line4, full_velocity_button=self._accent_button, priority=consts.MODAL_DIALOG_PRIORITY)
        note_editor_settings.mode_selector_layer = Layer(select_buttons=self._select_buttons, state_buttons=self._track_state_buttons, display_line=self._display_line4, priority=consts.MODAL_DIALOG_PRIORITY)
        self._note_editor_settings.append(NamedTuple(component=note_editor_settings, track_automation_layer=Layer(name_display_line=self._display_line1, graphic_display_line=self._display_line2, value_display_line=self._display_line3, priority=consts.MODAL_DIALOG_PRIORITY), device_automation_layer=Layer(name_display_line=self._display_line1, value_display_line=self._display_line2, graphic_display_line=self._display_line3, priority=consts.MODAL_DIALOG_PRIORITY)))
        return note_editor_settings

    def _init_instrument(self):
        instrument_basic_layer = Layer(octave_strip=ComboElement(self._touch_strip_control, [self._shift_button]), scales_toggle_button=self._scale_presets_button, presets_toggle_button=self._shift_button, octave_up_button=self._octave_up_button, octave_down_button=self._octave_down_button, scale_up_button=ComboElement(self._octave_up_button, [self._shift_button]), scale_down_button=ComboElement(self._octave_down_button, [self._shift_button]))
        self._instrument = MelodicComponent(skin=self._skin, is_enabled=False, clip_creator=self._clip_creator, name='Melodic_Component', grid_resolution=self._grid_resolution, note_editor_settings=self._add_note_editor_setting(), layer=Layer(playhead=self._playhead_element, mute_button=self._global_mute_button, quantization_buttons=self._side_buttons, loop_selector_matrix=self._double_press_matrix.submatrix[:, 0], short_loop_selector_matrix=self._double_press_event_matrix.submatrix[:, 0], note_editor_matrices=ButtonMatrixElement([[ self._matrix.submatrix[:, 7 - row] for row in xrange(7) ]])), instrument_play_layer=instrument_basic_layer + Layer(matrix=self._matrix, touch_strip=self._touch_strip_control, aftertouch_control=self._aftertouch_control, delete_button=self._delete_button), instrument_sequence_layer=instrument_basic_layer + Layer(note_strip=self._touch_strip_control))
        self._on_note_editor_layout_changed.subject = self._instrument

    def _init_scales(self):
        self._instrument.scales.layer = Layer(modus_line1=self._display_line1.subdisplay[:18], modus_line2=self._display_line2.subdisplay[:18], modus_line3=self._display_line3.subdisplay[:9], modus_line4=self._display_line4.subdisplay[:9], top_display_line=self._display_line3.subdisplay[9:], bottom_display_line=self._display_line4.subdisplay[9:], top_buttons=self._select_buttons, bottom_buttons=self._track_state_buttons, encoder_controls=self._global_param_controls, _blank_line1=Resetting(self._display_line1.subdisplay[18:]), _blank_line2=Resetting(self._display_line2.subdisplay[18:]), _notification=self._notification.use_single_line(0, get_slice[18:], align_right), priority=consts.MODAL_DIALOG_PRIORITY)
        self._instrument.scales.presets_layer = Layer(top_display_line=self._display_line3, bottom_display_line=self._display_line4, top_buttons=self._select_buttons, _bottom_buttons=Resetting(self._track_state_buttons), _encoders=Resetting(self._global_param_controls), _blank_line1=Resetting(self._display_line1), _blank_line2=Resetting(self._display_line2), _notification=self._notification.use_single_line(0), priority=consts.DIALOG_PRIORITY)

    def _init_step_sequencer(self):
        self._step_sequencer = StepSeqComponent(self._clip_creator, self._skin, name='Step_Sequencer', grid_resolution=self._grid_resolution, note_editor_settings=self._add_note_editor_setting())
        self._step_sequencer._drum_group._do_select_drum_pad = self._selector.on_select_drum_pad
        self._step_sequencer._drum_group._do_quantize_pitch = self._quantize.quantize_pitch
        self._step_sequencer.set_enabled(False)
        self._step_sequencer.layer = Layer(playhead=self._playhead_element, button_matrix=self._matrix.submatrix[:8, :4], drum_matrix=self._matrix.submatrix[:4, 4:8], loop_selector_matrix=self._double_press_matrix.submatrix[4:8, 4:8], short_loop_selector_matrix=self._double_press_event_matrix.submatrix[4:8, 4:8], touch_strip=self._touch_strip_control, detail_touch_strip=ComboElement(self._touch_strip_control, [self._shift_button]), quantization_buttons=self._side_buttons, solo_button=self._global_solo_button, select_button=self._select_button, delete_button=self._delete_button, shift_button=self._shift_button, drum_bank_up_button=self._octave_up_button, drum_bank_down_button=self._octave_down_button, quantize_button=self._quantize_button, mute_button=self._global_mute_button, drum_bank_detail_up_button=ComboElement(self._octave_up_button, [self._shift_button]), drum_bank_detail_down_button=ComboElement(self._octave_down_button, [self._shift_button]))
        self._audio_loop = LoopSelectorComponent(follow_detail_clip=True, measure_length=1.0, name='Loop_Selector')
        self._audio_loop.set_enabled(False)
        self._audio_loop.layer = Layer(loop_selector_matrix=self._matrix)

    def _init_note_repeat(self):
        self._note_repeat = NoteRepeatComponent(name='Note_Repeat')
        self._note_repeat.set_enabled(False)
        self._note_repeat.set_note_repeat(self._c_instance.note_repeat)
        self._note_repeat.layer = Layer(aftertouch_control=self._aftertouch_control, select_buttons=self._side_buttons)
        self._note_repeat.layer.priority = consts.DIALOG_PRIORITY
        self._note_repeat_enabler = EnablingModesComponent(name='Note_Repeat_Enabler', component=self._note_repeat, toggle_value='DiableButton.On')
        self._note_repeat_enabler.set_enabled(False)
        self._note_repeat_enabler.layer = Layer(toggle_button=self._repeat_button)

    def _init_message_box(self):
        self._notification = NotificationComponent(display_lines=self._display_lines)
        self._notification.set_enabled(True)
        self._dialog = DialogComponent()
        self._dialog.message_box_layer = Layer(display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, top_buttons=self._select_buttons, bottom_buttons=self._track_state_buttons, scales_button=self._scale_presets_button, octave_up=self._octave_up_button, octave_down=self._octave_down_button, side_buttons=self._side_buttons, repeat_button=self._repeat_button, accent_button=self._accent_button, in_button=self._in_button, out_button=self._out_button, param_controls=self._global_param_controls, param_touch=self._global_param_touch_buttons, tempo_control_tap=self._tempo_control_tap, master_control_tap=self._master_volume_control_tap, touch_strip=self._touch_strip_control, touch_strip_tap=self._touch_strip_tap, matrix=self._matrix, nav_up_button=self._nav_up_button, nav_down_button=self._nav_down_button, nav_left_button=self._nav_left_button, nav_right_button=self._nav_right_button, shift_button=self._shift_button, select_button=self._select_button, delete_button=self._delete_button, duplicate_button=self._duplicate_button, double_button=self._double_button, quantize_button=self._quantize_button, play_button=self._play_button, new_button=self._new_button, automation_button=self._automation_button, tap_tempo_button=self._tap_tempo_button, metronome_button=self._metronome_button, fixed_length_button=self._fixed_length_button, record_button=self._record_button, undo_button=self._undo_button, tempo_control=self._tempo_control, swing_control=self._swing_control, master_volume_control=self._master_volume_control, global_param_controls=self._global_param_controls, swing_control_tap=self._swing_control_tap, master_volume_tap=self._master_volume_control_tap, global_param_tap=self._global_param_touch_buttons, volumes_button=self._vol_mix_mode_button, pan_sends_button=self._pan_send_mix_mode_button, track_button=self._single_track_mix_mode_button, clip_button=self._clip_mode_button, device_button=self._device_mode_button, browse_button=self._browse_mode_button, user_button=self._user_button, master_select_button=self._master_select_button, create_device_button=self._create_device_button, create_track_button=self._create_track_button, global_track_stop_button=self._global_track_stop_button, global_mute_button=self._global_mute_button, global_solo_button=self._global_solo_button, note_mode_button=self._note_mode_button, session_mode_button=self._session_mode_button)
        self._dialog.message_box_layer.priority = consts.MESSAGE_BOX_PRIORITY
        self._dialog.set_enabled(True)

    def _for_non_frozen_tracks(self, component):
        """ Wrap component into a mode that will only enable it when
        the track is not frozen """
        TrackFrozenModesComponent(default_mode=component, frozen_mode=self._track_frozen_info)
        return component

    def _init_duplicate_actions(self):
        capture_element = ChoosingElement(self._duplicate_button, ComboElement(self._duplicate_button, [self._shift_button]), self._settings[SETTING_WORKFLOW])
        self._capture_and_insert_scene = CaptureAndInsertSceneComponent(name='Capture_And_Insert_Scene')
        self._capture_and_insert_scene.set_enabled(True)
        self._capture_and_insert_scene.layer = Layer(action_button=capture_element)
        duplicate_element = OptionalElement(ComboElement(self._duplicate_button, negative_modifiers=[self._shift_button]), self._settings[SETTING_WORKFLOW], False)
        self._duplicate_detail_clip = DuplicateDetailClipComponent(name='Duplicate_Detail_Clip')
        self._duplicate_detail_clip.set_enabled(True)
        self._duplicate_detail_clip.layer = Layer(action_button=duplicate_element)
        self._duplicate_loop = self._for_non_frozen_tracks(DuplicateLoopComponent(name='Duplicate_Loop', layer=Layer(action_button=self._double_button), is_enabled=False))

    def _init_delete_actions(self):
        self._delete_component = DeleteComponent(name='Deleter')
        self._delete_component.layer = Layer(delete_button=self._delete_button)
        self._delete_clip = DeleteSelectedClipComponent(name='Selected_Clip_Deleter')
        self._delete_clip.layer = Layer(action_button=self._delete_button)
        self._delete_scene = DeleteSelectedSceneComponent(name='Selected_Scene_Deleter')
        self._delete_scene.layer = Layer(action_button=ComboElement(self._delete_button, [self._shift_button]))

    def _init_quantize_actions(self):
        self._quantize = self._for_non_frozen_tracks(QuantizationComponent(name='Selected_Clip_Quantize', is_enabled=False, layer=Layer(action_button=self._quantize_button)))
        self._quantize.settings_layer = Layer(encoder_controls=self._global_param_controls, display_line1=self._display_line1, display_line2=self._display_line2, display_line3=self._display_line3, display_line4=self._display_line4, select_buttons=self._select_buttons, state_buttons=self._track_state_buttons)
        self._quantize.settings_layer.priority = consts.DIALOG_PRIORITY

    def _init_value_components(self):
        self._selector = SelectComponent(name='Selector')
        self._selector.layer = Layer(select_button=self._select_button)
        self._selector.selection_display_layer = Layer(display_line=self._display_line3)
        self._selector.selection_display_layer.priority = consts.DIALOG_PRIORITY
        self._swing_amount = ValueComponent('swing_amount', self.song(), display_label='Swing Amount:', display_format='%d%%', model_transform=lambda x: clamp(x / 200.0, 0.0, 0.5), view_transform=lambda x: x * 200.0, encoder_factor=100.0, encoder=self._swing_control)
        self._swing_amount.layer = Layer(button=self._swing_control_tap, encoder=self._swing_control)
        self._swing_amount.display_layer = Layer(label_display=self._display_line1, value_display=self._display_line3, graphic_display=self._display_line2, clear_display1=self._display_line4)
        self._swing_amount.display_layer.priority = consts.DIALOG_PRIORITY
        self._tempo = ValueComponent('tempo', self.song(), display_label='Tempo:', display_format='%0.2f BPM', encoder=self._tempo_control)
        self._tempo.layer = Layer(button=self._tempo_control_tap)
        self._tempo.display_layer = Layer(label_display=self._display_line1, value_display=self._display_line2, clear_display1=self._display_line3, clear_display2=self._display_line4)
        self._tempo.display_layer.priority = consts.DIALOG_PRIORITY
        self._master_vol = ParameterValueComponent(self.song().master_track.mixer_device.volume, display_label='Master Volume:', display_seg_start=3, name='Master_Volume_Display', encoder=self._master_volume_control)
        self._master_vol.layer = Layer(button=self._master_volume_control_tap)
        self._master_vol.display_layer = Layer(label_display=self._display_line1, value_display=self._display_line3, graphic_display=self._display_line2, clear_display2=self._display_line4)
        self._master_vol.display_layer.priority = consts.DIALOG_PRIORITY
        self._master_cue_vol = ParameterValueComponent(self.song().master_track.mixer_device.cue_volume, display_label='Cue Volume:', display_seg_start=3, name='Cue_Volume_Display', encoder=ComboElement(self._master_volume_control, [self._shift_button]))
        self._master_cue_vol.layer = Layer(button=ComboElement(self._master_volume_control_tap, [self._shift_button]))
        self._master_cue_vol.display_layer = Layer(label_display=self._display_line1, value_display=self._display_line3, graphic_display=self._display_line2, clear_display2=self._display_line4)
        self._master_cue_vol.display_layer.priority = consts.DIALOG_PRIORITY
        self._value_components = [self._swing_amount,
         self._tempo,
         self._master_vol,
         self._master_cue_vol]

    def _init_m4l_interface(self):
        self._m4l_interface = M4LInterfaceComponent(controls=self.controls, component_guard=self.component_guard)
        self.get_control_names = self._m4l_interface.get_control_names
        self.get_control = self._m4l_interface.get_control
        self.grab_control = self._m4l_interface.grab_control
        self.release_control = self._m4l_interface.release_control

    @subject_slot('selected_mode')
    def _on_note_editor_layout_changed(self, mode):
        self.reset_controlled_track(mode)

    def reset_controlled_track(self, mode = None):
        if mode == None:
            mode = self._instrument.selected_mode
        if self._instrument.is_enabled() and mode == 'sequence':
            self.release_controlled_track()
        else:
            self.set_controlled_track(self.song().view.selected_track)

    @subject_slot('selected_track.is_frozen')
    def _on_selected_track_is_frozen_changed(self):
        self._select_note_mode()

    def _on_selected_track_changed(self):
        super(Push, self)._on_selected_track_changed()
        self.reset_controlled_track()
        self._select_note_mode()
        self._main_modes.pop_groups(['add_effect'])
        self._note_repeat_enabler.selected_mode = 'disabled'

    def _send_midi(self, midi_event_bytes, optimized = True):
        if not self._suppress_sysex or not self.is_sysex_message(midi_event_bytes):
            return super(Push, self)._send_midi(midi_event_bytes, optimized)

    @subject_slot('session_record')
    def _on_session_record_changed(self):
        status = self.song().session_record
        playhead_color = 'PlayheadRecord' if status else 'Playhead'
        feedback_color = int(self._skin['Instrument.FeedbackRecord'] if status else self._skin['Instrument.Feedback'])
        self._instrument.playhead_color = playhead_color
        self._step_sequencer.playhead_color = playhead_color
        self._c_instance.set_feedback_velocity(feedback_color)

    @subject_slot('selected_mode')
    def _on_accent_mode_changed(self, mode_name):
        accent_is_active = mode_name == 'enabled'
        self._step_sequencer.full_velocity = accent_is_active
        self._instrument.full_velocity = accent_is_active

    @subject_slot('value')
    def _on_pad_threshold(self, setting):
        self._user.set_settings_info_text('' if setting.value >= consts.CRITICAL_THRESHOLD_LIMIT else consts.MessageBoxText.STUCK_PAD_WARNING)
        self._update_pad_params()

    @subject_slot('value')
    def _on_pad_curve(self, setting):
        self._update_pad_params()

    def _update_pad_params(self):
        new_pad_parameters = make_pad_parameters(self._settings[SETTING_CURVE].value, self._settings[SETTING_THRESHOLD].value)
        self._pad_sensitivity_update.set_profile('instrument', new_pad_parameters)
        self._pad_sensitivity_update.set_profile('drums', new_pad_parameters)

    @subject_slot('before_mode_sent')
    def _on_before_hardware_mode_sent(self, mode):
        self._suppress_sysex = False

    @subject_slot('after_mode_sent')
    def _on_after_hardware_mode_sent(self, mode):
        if mode == Sysex.USER_MODE:
            self._suppress_sysex = True

    @subject_slot('mode')
    def _on_hardware_mode_changed(self, mode):
        if mode == Sysex.LIVE_MODE:
            self.update()
        elif mode == Sysex.USER_MODE:
            self._suppress_sysex = True
        self._update_auto_arm()

    @subject_slot('selected_mode')
    def _on_matrix_mode_changed(self, mode):
        self._update_auto_arm(selected_mode=mode)

    def _update_auto_arm(self, selected_mode = None):
        self._auto_arm.set_enabled(self._user.mode == Sysex.LIVE_MODE and (selected_mode or self._matrix_modes.selected_mode == 'note'))

    @subject_slot('drum_group')
    def _on_drum_group_changed(self):
        self._select_note_mode()

    def _select_note_mode(self):
        """
        Selects which note mode to use depending on the kind of
        current selected track and its device chain...
        """
        track = self.song().view.selected_track
        drum_device = self._drum_group_finder.drum_group
        self._step_sequencer.set_drum_group_device(drum_device)
        if track == None or track.is_foldable or track in self.song().return_tracks or track == self.song().master_track or track.is_frozen:
            self._note_modes.selected_mode = 'disabled'
        elif track and track.has_audio_input:
            self._note_modes.selected_mode = 'looper'
        elif drum_device:
            self._note_modes.selected_mode = 'sequencer'
        else:
            self._note_modes.selected_mode = 'instrument'
        self.reset_controlled_track()

    def _on_toggle_encoder(self, value):
        pass

    @subject_slot_group('value')
    def _on_param_encoder_touched(self, value, encoder):
        """
        When using the parameter encoders, other encoders around it are often accidentally
        touched and will take over the screen. By putting all ValueComponents into timer
        based displaying mode while touching a parameter, this noise is prevented.
        """
        param_encoder_touched = find_if(lambda encoder: encoder.is_pressed(), self._global_param_touch_buttons_raw) != None
        new_display_mode = ValueComponent.TIMER_BASED if param_encoder_touched else ValueComponent.TOUCH_BASED
        for value_component in self._value_components:
            value_component.display_mode = new_display_mode

    def expect_dialog(self, message):
        self.schedule_message(1, partial(self._dialog.expect_dialog, message))

    def show_notification(self, message):
        self._notification.show_notification(message)

    def handle_nonsysex(self, midi_bytes):
        _, _, value = midi_bytes
        recipient = self.get_recipient_for_nonsysex_midi_message(midi_bytes)
        if isinstance(recipient, ButtonElement) and value != 0:
            self._notification.hide_notification()
            with self._double_press_context.breaking_double_press():
                super(Push, self).handle_nonsysex(midi_bytes)
        else:
            super(Push, self).handle_nonsysex(midi_bytes)