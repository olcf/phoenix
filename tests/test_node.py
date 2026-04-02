import pytest

from phoenix.node import Node
from phoenix.node import NodeLayer
from phoenix.node import NodeLayerMap

data1={ 'key1': 'valueA',
        'key2': 'valueB',
        'mapping1': { 'key3': 'valueC',
                      'key4': 'valueD',
                    }
      }
data2={ 'key2': 'valueE',
        'mapping1': { 'key3': 'valueF',
                      'key5': 'valueG',
                    }
      }
datayaml = '''
'node[01-02]':
  key1: valueA
  key2: valueB
  mapping1:
    key3: valueC
    key4: valueD
node01:
  key2: valueE
  mapping1:
    key3: valueF
    key5: valueG
rack2node3:
  plugin: generic
  key6: '{{name}}-templated'
  mapping2:
    key7: 'hello-{{name}}'
'''

def test_nodelayermap():
    n1 = NodeLayerMap()

    a = NodeLayer(layertype="manual",
                  noderange='node[01-02]',
                  data=data1,
                 )
    b = NodeLayer(layertype="manual",
                  noderange='node01',
                  data=data2,
                 )
    n1.addlayer(a)
    n1.addlayer(b)

    assert n1['key1'] == 'valueA'
    assert n1['key2'] == 'valueE'
    assert n1['mapping1']['key3'] == 'valueF'
    assert n1['mapping1']['key4'] == 'valueD'
    assert n1['mapping1']['key5'] == 'valueG'

def test_node_inheritance():
    Node.load_nodes(datastr=datayaml, clear=True)
    n1 = Node.find_node('node01')
    n2 = Node.find_node('node02')

    assert n1['key1'] == 'valueA'
    assert n2['key1'] == 'valueA'
    assert n1['key2'] == 'valueE'
    assert n2['key2'] == 'valueB'
    assert n1['mapping1']['key3'] == 'valueF'
    assert n1['mapping1']['key4'] == 'valueD'
    assert n1['mapping1']['key5'] == 'valueG'

def test_node_plugin_generic():
    Node.load_nodes(datastr=datayaml, clear=True)
    n2 = Node.find_node('node02')
    n3 = Node.find_node('rack2node3')

    assert n2['plugin'] == 'generic'
    assert n2['nodeindex'] == 2
    assert n3['plugin'] == 'generic'
    assert n3['nodeindex'] == 3
    assert n3['nodenums'] == [2,3]

    print(n2)

def test_node_templates():
    Node.load_nodes(datastr=datayaml, clear=True)
    n3 = Node.find_node('rack2node3')
    assert n3['key6'] == 'rack2node3-templated'
    assert n3['mapping2']['key7'] == 'hello-rack2node3'
    #print(dict(n3))
    print(n3)
