import pytest

from phoenix.node import Node
from phoenix.oob.redfish import RedfishBmc, RedfishPdu

nodesyaml = '''
inline:
  bmc: bmc1
actioninfo:
  bmc: bmc2
configured:
  bmc: bmc1
  redfishpath: Systems/Node0
  redfish_actions: [On, Off, Contoso.Ping]
mapped:
  bmc: bmc1
  redfishpath: Systems/Node0
  redfish_actions:
    Off: Systems/Node0/Actions/Custom.Reset
    Contoso.Mode:
      target: Systems/Node0/Actions/Oem/Contoso.Mode
      parameters:
        Mode: [Fast, Slow]
nomanageractions:
  bmc: bmc1
  redfishpath: Systems/1
  redfish_manager_path: Systems/Missing
chassis:
  bmc: bmc2
  pdu: bmc2
  pdutype: redfish
  pduredfishpath: Chassis/Board0
oem:
  bmc: bmc3
enclosure:
  pdu: bmc3
  pdutype: redfish
  pduredfishpath: Chassis/Enc
'''

# Reset types listed inline with AllowableValues, plus an OEM action
INLINE = {
    'Systems': {'Members': [{'@odata.id': '/redfish/v1/Systems/1'}]},
    'Systems/1': {
        'PowerState': 'On',
        'Links': {'ManagedBy': [{'@odata.id': '/redfish/v1/Managers/BMC'}]},
        'Actions': {
            '#ComputerSystem.Reset': {
                'target': '/redfish/v1/Systems/1/Actions/ComputerSystem.Reset',
                'ResetType@Redfish.AllowableValues': ['On', 'ForceOff', 'GracefulRestart'],
            },
            'Oem': {
                '#Contoso.Ping': {'target': '/redfish/v1/Systems/1/Actions/Oem/Contoso.Ping'},
            },
        },
    },
    'Managers/BMC': {
        'PowerState': 'On',
        'Actions': {
            '#Manager.Reset': {
                'target': '/redfish/v1/Managers/BMC/Actions/Manager.Reset',
                '@Redfish.ActionInfo': '/redfish/v1/Managers/BMC/ResetActionInfo',
            },
        },
    },
    'Managers/BMC/ResetActionInfo': {
        'Parameters': [{'Name': 'ResetType', 'AllowableValues': ['ForceRestart', 'GracefulRestart']}],
    },
}

# Reset types only available via ActionInfo, chassis resets, and standard
# non-reset manager actions that take parameters
ACTIONINFO = {
    'Systems': {'Members': [{'@odata.id': '/redfish/v1/Systems/system'}]},
    'Systems/system': {
        'PowerState': 'On',
        'Links': {
            'ManagedBy': [{'@odata.id': '/redfish/v1/Managers/bmc'}],
            'Chassis': [{'@odata.id': '/redfish/v1/Chassis/Board0'}],
        },
        'Actions': {
            '#ComputerSystem.Reset': {
                '@Redfish.ActionInfo': '/redfish/v1/Systems/system/ResetActionInfo',
                'target': '/redfish/v1/Systems/system/Actions/ComputerSystem.Reset',
            },
        },
    },
    'Systems/system/ResetActionInfo': {
        'Parameters': [{'Name': 'ResetType', 'Required': True, 'AllowableValues':
            ['On', 'ForceOff', 'ForceOn', 'ForceRestart', 'GracefulRestart', 'GracefulShutdown', 'PowerCycle', 'Nmi']}],
    },
    'Managers/bmc': {
        'PowerState': 'On',
        'Actions': {
            '#Manager.Reset': {
                '@Redfish.ActionInfo': '/redfish/v1/Managers/bmc/ResetActionInfo',
                'target': '/redfish/v1/Managers/bmc/Actions/Manager.Reset',
            },
            '#Manager.ResetToDefaults': {
                'ResetType@Redfish.AllowableValues': ['ResetAll'],
                'target': '/redfish/v1/Managers/bmc/Actions/Manager.ResetToDefaults',
            },
            '#Manager.SetWidgetService': {
                'SetType@Redfish.AllowableValues': ['Start', 'Stop', 'Enable', 'Disable'],
                'target': '/redfish/v1/Managers/bmc/Actions/Manager.SetWidgetService',
            },
        },
    },
    'Managers/bmc/ResetActionInfo': {
        'Parameters': [{'Name': 'ResetType', 'Required': True, 'AllowableValues': ['GracefulRestart', 'ForceRestart']}],
    },
    'Chassis/Board0': {
        'PowerState': 'On',
        'Actions': {
            '#Chassis.Reset': {
                '@Redfish.ActionInfo': '/redfish/v1/Chassis/Board0/ResetActionInfo',
                'target': '/redfish/v1/Chassis/Board0/Actions/Chassis.Reset',
            },
        },
    },
    'Chassis/Board0/ResetActionInfo': {
        'Parameters': [{'Name': 'ResetType', 'Required': True, 'AllowableValues': ['PowerCycle']}],
    },
}

# OEM action layouts: vendor-nested, dotless names, OEM actions under a
# standard resource type name, OEM actions with ResetType or boolean
# parameters, and ActionInfo without Parameters or that fails to load
OEM = {
    'Systems': {'Members': [{'@odata.id': '/redfish/v1/Systems/Sys0'}]},
    'Systems/Sys0': {
        'PowerState': 'On',
        'Actions': {
            '#ComputerSystem.Reset': {
                'ResetType@Redfish.AllowableValues': ['PushPowerButton', 'On', 'ForceOff'],
                'target': '/redfish/v1/Systems/Sys0/Actions/ComputerSystem.Reset',
            },
            'Oem': {
                '#Contoso.Oem.Erase': {
                    'Keys@Redfish.AllowableValues': [True, False],
                    'target': '/redfish/v1/Systems/Sys0/Actions/Oem/Contoso.Oem.Erase',
                },
                '#Lock': {'target': '/redfish/v1/Systems/Sys0/Actions/Oem/Lock'},
            },
        },
    },
    'Chassis/Enc': {
        'PowerState': 'On',
        'Actions': {
            '#Chassis.Reset': {
                'ResetType@Redfish.AllowableValues': ['ForceOff', 'On', 'Off'],
                'target': '/redfish/v1/Chassis/Enc/Actions/Chassis.Reset',
            },
            'Oem': {
                '#Chassis.Emergency': {
                    'ResetType@Redfish.AllowableValues': ['ForceOff'],
                    'target': '/redfish/v1/Chassis/Enc/Actions/Oem/Chassis.Emergency',
                },
                '#ContosoChassis.AuxReset': {
                    '@Redfish.ActionInfo': '/redfish/v1/Chassis/Enc/Oem/AuxResetActionInfo',
                    'target': '/redfish/v1/Chassis/Enc/Actions/Oem/ContosoChassis.AuxReset',
                },
            },
        },
    },
    'Chassis/Enc/Oem/AuxResetActionInfo': {
        'Parameters': [{'Name': 'ResetType', 'Required': True, 'AllowableValues': ['AuxPowerCycle']}],
    },
    'Managers': {'Members': [{'@odata.id': '/redfish/v1/Managers/M0'}]},
    'Managers/M0': {
        'Actions': {
            '#Manager.Reset': {
                'ResetType@Redfish.AllowableValues': ['ForceRestart', 'StatefulReset'],
                'target': '/redfish/v1/Managers/M0/Actions/Manager.Reset',
            },
            'Oem': {
                '#ContosoManager.ResetToDefaults': {
                    'target': '/redfish/v1/Managers/M0/Actions/Oem/ContosoManager.ResetToDefaults',
                },
                '#Disk.Erase': {
                    '@Redfish.ActionInfo': '/redfish/v1/Managers/M0/Oem/EraseActionInfo',
                    'target': '/redfish/v1/Managers/M0/Actions/Oem/Disk.Erase',
                },
                '#Contoso.Process': {
                    'Name@Redfish.AllowableValues': ['memtest', 'burn'],
                    'target': '/redfish/v1/Managers/M0/Actions/Oem/Contoso.Process',
                },
                'Contoso': {
                    '#ContosoManager.RawCommand': {
                        '@Redfish.ActionInfo': '/redfish/v1/Managers/M0/Oem/Contoso/RawCommandActionInfo',
                        'target': '/redfish/v1/Managers/M0/Actions/Oem/ContosoManager.RawCommand',
                    },
                },
            },
        },
    },
    'Managers/M0/Oem/EraseActionInfo': {'Id': 'EraseActionInfo'},
}

HOSTS = {'bmc1': INLINE, 'bmc2': ACTIONINFO, 'bmc3': OEM}

class FakeResponse(object):
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body
        self.text = '' if body is None else str(body)
        self.content = self.text.encode()

    def json(self):
        return self._body

class FakeClient(object):
    def __init__(self):
        self.state = None
        self.messages = []

    def set_state(self, state):
        self.state = state

    def output(self, message, stderr=False):
        self.messages.append((message, stderr))

@pytest.fixture
def bmc(monkeypatch):
    calls = []
    def fake_req(cls, host, path, request_type, auth=None, data={}, headers={}, timeout=None, expand=False):
        calls.append((request_type, path, data))
        if request_type == 'get':
            resources = HOSTS[host]
            return FakeResponse(200, resources[path]) if path in resources else FakeResponse(404)
        return FakeResponse(204)
    monkeypatch.setattr(RedfishBmc, '_do_redfish_req', classmethod(fake_req))
    monkeypatch.setattr(RedfishPdu, '_do_redfish_req', classmethod(fake_req))
    Node.load_nodes(datastr=nodesyaml, clear=True)
    return calls

def posts(calls):
    return [(path, data) for (method, path, data) in calls if method == 'post']

def gets(calls):
    return [path for (method, path, data) in calls if method == 'get']

def test_discover_and_cache(bmc):
    node = Node.find_node('inline')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['forceoff']) == 0
    assert posts(bmc) == [('Systems/1/Actions/ComputerSystem.Reset', {'ResetType': 'ForceOff'})]
    assert set(node['redfish_actions']) == {'On', 'ForceOff', 'GracefulRestart', 'Contoso.Ping'}

    del bmc[:]
    assert RedfishBmc.power(node, client, ['ON']) == 0
    assert gets(bmc) == []

def test_oem_action(bmc):
    node = Node.find_node('inline')
    assert RedfishBmc.power(node, FakeClient(), ['contoso.ping']) == 0
    assert posts(bmc) == [('Systems/1/Actions/Oem/Contoso.Ping', {})]

def test_unsupported_action_rejected(bmc):
    node = Node.find_node('inline')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['Nmi']) == 1
    assert posts(bmc) == []
    assert client.messages[-1][1] is True

def test_force_skips_check(bmc):
    node = Node.find_node('inline')
    assert RedfishBmc.power(node, FakeClient(), ['Nmi'], force=True) == 0
    assert RedfishBmc.power(node, FakeClient(), ['Contoso.Other', 'Key=Value'], force=True) == 0
    assert posts(bmc) == [
        ('Systems/1/Actions/ComputerSystem.Reset', {'ResetType': 'Nmi'}),
        ('Systems/1/Actions/Oem/Contoso.Other', {'Key': 'Value'}),
    ]
    assert gets(bmc) == ['Systems']

def test_configured_list(bmc):
    node = Node.find_node('configured')
    assert RedfishBmc.power(node, FakeClient(), ['on']) == 0
    assert RedfishBmc.power(node, FakeClient(), ['off']) == 0
    assert RedfishBmc.power(node, FakeClient(), ['contoso.ping']) == 0
    assert RedfishBmc.power(node, FakeClient(), ['ForceOff']) == 1
    assert posts(bmc) == [
        ('Systems/Node0/Actions/ComputerSystem.Reset', {'ResetType': 'On'}),
        ('Systems/Node0/Actions/ComputerSystem.Reset', {'ResetType': 'Off'}),
        ('Systems/Node0/Actions/Oem/Contoso.Ping', {}),
    ]
    assert gets(bmc) == []

def test_configured_mapping(bmc):
    node = Node.find_node('mapped')
    assert RedfishBmc.power(node, FakeClient(), ['OFF']) == 0
    assert RedfishBmc.power(node, FakeClient(), ['contoso.mode', 'fast']) == 0
    assert RedfishBmc.power(node, FakeClient(), ['contoso.mode', 'Medium']) == 1
    assert posts(bmc) == [
        ('Systems/Node0/Actions/Custom.Reset', {'ResetType': 'Off'}),
        ('Systems/Node0/Actions/Oem/Contoso.Mode', {'Mode': 'Fast'}),
    ]

def test_manager(bmc):
    node = Node.find_node('inline')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='manager') == 0
    assert client.state == 'ForceRestart, GracefulRestart'
    assert RedfishBmc.power(node, client, ['forcerestart'], target='manager') == 0
    assert posts(bmc) == [('Managers/BMC/Actions/Manager.Reset', {'ResetType': 'ForceRestart'})]
    assert node['redfish_manager_path'] == 'Managers/BMC'

def test_system_actioninfo(bmc):
    node = Node.find_node('actioninfo')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions']) == 0
    assert client.state == 'ForceOff, ForceOn, ForceRestart, GracefulRestart, GracefulShutdown, Nmi, On, PowerCycle'
    assert RedfishBmc.power(node, client, ['powercycle']) == 0
    assert posts(bmc) == [('Systems/system/Actions/ComputerSystem.Reset', {'ResetType': 'PowerCycle'})]

def test_manager_standard_actions(bmc):
    node = Node.find_node('actioninfo')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='manager') == 0
    assert client.state == ('ForceRestart, GracefulRestart, '
                            'Manager.ResetToDefaults(ResetType=ResetAll), '
                            'Manager.SetWidgetService(SetType=Start|Stop|Enable|Disable)')
    assert RedfishBmc.power(node, client, ['manager.resettodefaults', 'resetall'], target='manager') == 0
    assert RedfishBmc.power(node, client, ['Manager.SetWidgetService', 'settype=STOP'], target='manager') == 0
    assert posts(bmc) == [
        ('Managers/bmc/Actions/Manager.ResetToDefaults', {'ResetType': 'ResetAll'}),
        ('Managers/bmc/Actions/Manager.SetWidgetService', {'SetType': 'Stop'}),
    ]

def test_action_parameter_errors(bmc):
    node = Node.find_node('actioninfo')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['Manager.SetWidgetService'], target='manager') == 1
    assert 'Missing parameter' in client.state
    assert RedfishBmc.power(node, client, ['Manager.SetWidgetService', 'Restart'], target='manager') == 1
    assert 'Invalid value' in client.state
    assert RedfishBmc.power(node, client, ['Manager.SetWidgetService', 'Bogus=Stop'], target='manager') == 1
    assert 'Unknown parameter' in client.state
    assert RedfishBmc.power(node, client, ['ForceRestart', 'Now'], target='manager') == 1
    assert 'does not take parameters' in client.state
    assert posts(bmc) == []

def test_default_targets():
    assert RedfishBmc._redfish_default_target('Systems/1', 'On') == 'Systems/1/Actions/ComputerSystem.Reset'
    assert RedfishBmc._redfish_default_target('Chassis/Blade0', 'Off') == 'Chassis/Blade0/Actions/Chassis.Reset'
    assert RedfishBmc._redfish_default_target('Managers/bmc', 'ForceRestart') == 'Managers/bmc/Actions/Manager.Reset'
    assert RedfishBmc._redfish_default_target('Managers/bmc', 'Manager.ResetToDefaults') == 'Managers/bmc/Actions/Manager.ResetToDefaults'
    assert RedfishBmc._redfish_default_target('Systems/1', 'Contoso.Ping') == 'Systems/1/Actions/Oem/Contoso.Ping'

def test_pdu_chassis(bmc):
    node = Node.find_node('chassis')
    client = FakeClient()
    assert RedfishPdu.power(node, client, ['actions']) == 0
    assert client.state == 'PowerCycle'
    assert RedfishPdu.power(node, client, ['powercycle']) == 0
    assert posts(bmc) == [('Chassis/Board0/Actions/Chassis.Reset', {'ResetType': 'PowerCycle'})]
    assert 'pdu_redfish_actions' in node
    assert 'redfish_actions' not in node

def test_oem_system_actions(bmc):
    node = Node.find_node('oem')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions']) == 0
    assert client.state == 'Contoso.Oem.Erase(Keys=true|false), ForceOff, Lock, On, PushPowerButton'
    assert RedfishBmc.power(node, client, ['pushpowerbutton']) == 0
    assert RedfishBmc.power(node, client, ['lock']) == 0
    assert RedfishBmc.power(node, client, ['contoso.oem.erase', 'False']) == 0
    assert posts(bmc) == [
        ('Systems/Sys0/Actions/ComputerSystem.Reset', {'ResetType': 'PushPowerButton'}),
        ('Systems/Sys0/Actions/Oem/Lock', {}),
        ('Systems/Sys0/Actions/Oem/Contoso.Oem.Erase', {'Keys': False}),
    ]

def test_oem_manager_actions(bmc):
    node = Node.find_node('oem')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='manager') == 0
    assert client.state == ('Contoso.Process(Name=memtest|burn), ContosoManager.RawCommand, '
                            'ContosoManager.ResetToDefaults, Disk.Erase, ForceRestart, StatefulReset')
    assert RedfishBmc.power(node, client, ['statefulreset'], target='manager') == 0
    assert RedfishBmc.power(node, client, ['contoso.process', 'MEMTEST'], target='manager') == 0
    assert RedfishBmc.power(node, client, ['ContosoManager.RawCommand'], target='manager') == 0
    assert posts(bmc) == [
        ('Managers/M0/Actions/Manager.Reset', {'ResetType': 'StatefulReset'}),
        ('Managers/M0/Actions/Oem/Contoso.Process', {'Name': 'memtest'}),
        ('Managers/M0/Actions/Oem/ContosoManager.RawCommand', {}),
    ]

def test_oem_chassis_reset_actions(bmc):
    node = Node.find_node('enclosure')
    client = FakeClient()
    assert RedfishPdu.power(node, client, ['actions']) == 0
    assert client.state == ('Chassis.Emergency(ResetType=ForceOff), ContosoChassis.AuxReset(ResetType=AuxPowerCycle), '
                            'ForceOff, Off, On')
    assert RedfishPdu.power(node, client, ['off']) == 0
    assert RedfishPdu.power(node, client, ['chassis.emergency']) == 1
    assert RedfishPdu.power(node, client, ['chassis.emergency', 'forceoff']) == 0
    assert RedfishPdu.power(node, client, ['ContosoChassis.AuxReset', 'ResetType=AuxPowerCycle']) == 0
    assert posts(bmc) == [
        ('Chassis/Enc/Actions/Chassis.Reset', {'ResetType': 'Off'}),
        ('Chassis/Enc/Actions/Oem/Chassis.Emergency', {'ResetType': 'ForceOff'}),
        ('Chassis/Enc/Actions/Oem/ContosoChassis.AuxReset', {'ResetType': 'AuxPowerCycle'}),
    ]

def test_force_dotless_oem(bmc):
    node = Node.find_node('oem')
    assert RedfishBmc.power(node, FakeClient(), ['Chassis.Unknown'], force=True) == 0
    assert posts(bmc) == [('Systems/Sys0/Actions/Oem/Chassis.Unknown', {})]

def test_chassis(bmc):
    node = Node.find_node('actioninfo')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='chassis') == 0
    assert client.state == 'PowerCycle'
    assert RedfishBmc.power(node, client, ['stat'], target='chassis') == 0
    assert client.state == 'On'
    assert RedfishBmc.power(node, client, ['powercycle'], target='chassis') == 0
    assert posts(bmc) == [('Chassis/Board0/Actions/Chassis.Reset', {'ResetType': 'PowerCycle'})]
    assert node['redfish_chassis_path'] == 'Chassis/Board0'
    assert 'redfish_chassis_actions' in node

def test_explicit_target(bmc):
    node = Node.find_node('oem')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='/redfish/v1/Chassis/Enc') == 0
    assert 'Chassis.Emergency' in client.state
    assert RedfishBmc.power(node, client, ['on'], target='Chassis/Enc') == 0
    assert RedfishBmc.power(node, client, ['ForceRestart'], target='Chassis/Enc', force=True) == 0
    assert posts(bmc) == [
        ('Chassis/Enc/Actions/Chassis.Reset', {'ResetType': 'On'}),
        ('Chassis/Enc/Actions/Chassis.Reset', {'ResetType': 'ForceRestart'}),
    ]
    assert 'redfish_actions' not in node
    assert 'redfish_chassis_actions' not in node

def test_no_actions_found(bmc):
    node = Node.find_node('nomanageractions')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], target='manager') == 1
    assert RedfishBmc.power(node, client, ['ForceRestart'], target='manager') == 1
    assert posts(bmc) == []
    assert 'redfish_manager_actions' not in node

def test_actions_yaml(bmc):
    import yaml
    node = Node.find_node('inline')
    client = FakeClient()
    assert RedfishBmc.power(node, client, ['actions'], as_yaml=True) == 0
    assert client.state == ('redfishpath: Systems/1\n'
                            'redfish_actions: [Contoso.Ping, ForceOff, GracefulRestart, \'On\']')
    assert RedfishBmc.power(node, client, ['actions'], target='manager', as_yaml=True) == 0
    assert client.state == ('redfish_manager_path: Managers/BMC\n'
                            'redfish_manager_actions: [ForceRestart, GracefulRestart]')

    node = Node.find_node('oem')
    assert RedfishBmc.power(node, client, ['actions'], target='manager', as_yaml=True) == 0
    dumped = client.state
    attrs = yaml.safe_load(dumped)
    actions = attrs['redfish_manager_actions']
    assert actions['ForceRestart'] is None
    assert actions['Contoso.Process'] == {'parameters': {'Name': ['memtest', 'burn']}}
    assert actions['ContosoManager.RawCommand'] is None

    assert RedfishBmc.power(Node.find_node('mapped'), client, ['actions'], as_yaml=True) == 0
    assert yaml.safe_load(client.state)['redfish_actions'] == {
        'Off': 'Systems/Node0/Actions/Custom.Reset',
        'Contoso.Mode': {'parameters': {'Mode': ['Fast', 'Slow']}},
    }

    Node.load_nodes(datastr='copy:\n  bmc: bmc3\n'
                    + '\n'.join('  ' + line for line in dumped.splitlines()), clear=True)
    copy = Node.find_node('copy')
    del bmc[:]
    assert RedfishBmc.power(copy, client, ['actions'], target='manager', as_yaml=True) == 0
    assert yaml.safe_load(client.state) == attrs
    assert RedfishBmc.power(copy, client, ['contoso.process', 'burn'], target='manager') == 0
    assert RedfishBmc.power(copy, client, ['ContosoManager.RawCommand'], target='manager') == 0
    assert gets(bmc) == []
    assert posts(bmc) == [
        ('Managers/M0/Actions/Oem/Contoso.Process', {'Name': 'burn'}),
        ('Managers/M0/Actions/Oem/ContosoManager.RawCommand', {}),
    ]

def test_actions_yaml_pdu(bmc):
    node = Node.find_node('enclosure')
    client = FakeClient()
    assert RedfishPdu.power(node, client, ['actions'], as_yaml=True) == 0
    assert client.state.startswith('pduredfishpath: Chassis/Enc\npdu_redfish_actions:\n')
    assert RedfishPdu.power(node, client, ['actions'], target='Chassis/Enc', as_yaml=True) == 1

def test_wait(bmc, monkeypatch):
    monkeypatch.setattr('phoenix.oob.time.sleep', lambda s: None)
    node = Node.find_node('inline')
    client = FakeClient()
    assert RedfishBmc._wait_for_power_state(node, client, 'ON', timeout=2)
    assert not RedfishBmc._wait_for_power_state(node, client, 'Off', timeout=2)
