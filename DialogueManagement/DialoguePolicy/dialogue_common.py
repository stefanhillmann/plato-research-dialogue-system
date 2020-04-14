import json
import random
from copy import deepcopy
from typing import NamedTuple, List

from Dialogue.Action import DialogueAct, DialogueActItem, Operator
from Dialogue.State import SlotFillingDialogueState

STATE_DIM = 45

class Domain(NamedTuple):
    acts_params:List[str]=['inform','request']
    dstc2_acts_sys:List[str] = None
    dstc2_acts_usr:List[str] = None
    system_requestable_slots:List[str] = None
    requestable_slots:List[str] = None
    NActions:int=None
    
def setup_domain(ontology):
    # Extract lists of slots that are frequently used
    informable_slots = \
        deepcopy(list(ontology.ontology['informable'].keys()))
    requestable_slots = \
        deepcopy(ontology.ontology['requestable'])
    system_requestable_slots = \
        deepcopy(ontology.ontology['system_requestable'])

    dstc2_acts_sys = ['offer', 'canthelp', 'affirm',
                           'deny', 'ack', 'bye', 'reqmore',
                           'welcomemsg', 'expl-conf', 'select',
                           'repeat', 'confirm-domain',
                           'confirm']

    # Does not include inform and request that are modelled
    # together with their arguments
    dstc2_acts_usr = ['affirm', 'negate', 'deny', 'ack',
                           'thankyou', 'bye', 'reqmore',
                           'hello', 'expl-conf', 'repeat',
                           'reqalts', 'restart', 'confirm']

    dstc2_acts = dstc2_acts_sys
    NActions = len(dstc2_acts)  # system acts without parameters
    NActions += len(
        system_requestable_slots)  # system request with certain slots
    NActions += len(requestable_slots)  # system inform with certain slot

    return Domain(['inform','request'],dstc2_acts_sys, dstc2_acts_usr,
                         system_requestable_slots, requestable_slots,NActions)

def pick_some(x,num_min,num_max):
    num_to_pick = random.randint(num_min,num_max)
    random.shuffle(x)
    return x[:num_to_pick]

def create_random_dialog_act(domain:Domain,is_system=True):
    acts = []
    if is_system:
        inform_slots = domain.requestable_slots
        request_slots = domain.system_requestable_slots
    else:
        inform_slots = domain.system_requestable_slots
        request_slots = domain.requestable_slots

    intent_p = random.choice(domain.acts_params)
    if intent_p is not None:
        if intent_p == 'inform':
            slots = pick_some(inform_slots,1,1)
        elif intent_p == 'request':
            slots = pick_some(request_slots,1,1)
        else:
            assert False
        act = DialogueAct(intent_p,params=[DialogueActItem(slot,Operator.EQ,None) for slot in slots])
        acts.append(act)

    # if is_system:
    #     intens_w = pick_some(domain.dstc2_acts_sys,0,3)
    # else:
    #     intens_w = pick_some(domain.dstc2_acts_usr,0,3)
    # acts.extend([DialogueAct(i) for i in intens_w])
    return acts


def action_to_string(acts:List[DialogueAct], system):
    sys_usr = 'sys' if system else 'usr'

    def extract_features_from_act(act: DialogueAct):
        return (act.intent, [p.slot for p in act.params])

    strings = [json.dumps(extract_features_from_act(a)) for a in acts]
    s = sys_usr + ';'.join(strings)
    return s

def state_to_json(state:SlotFillingDialogueState)->str:
    temp = deepcopy(state)
    del temp.context
    del temp.system_requestable_slot_entropies
    del temp.db_result
    del temp.dialogStateUuid
    del temp.user_goal
    del temp.slots
    del temp.item_in_focus
    temp.db_matches_ratio = int(round(temp.db_matches_ratio, 2) * 100)
    temp.slots_filled = [s for s,v in temp.slots_filled.items() if v is not None]
    if temp.last_sys_acts is not None:
        temp.last_sys_acts = action_to_string(temp.last_sys_acts, system=True)
        temp.user_acts = action_to_string(temp.user_acts, system=False)

    d = todict(temp)
    assert d is not None
    # d['item_in_focus'] = [(k,d['item_in_focus'] is not None and d['item_in_focus'].get(k,None) is not None) for k in self.domain.requestable_slots]
    s = json.dumps(d)
    # state_enc = int(hashlib.sha1(s.encode('utf-8')).hexdigest(), 32)
    return s


def todict(obj, classkey=None):
    if isinstance(obj, dict):
        data = {}
        for (k, v) in obj.items():
            data[k] = todict(v, classkey)
        return data
    elif hasattr(obj, "_ast"):
        return todict(obj._ast())
    elif hasattr(obj, "__iter__") and not isinstance(obj, str):
        return [todict(v, classkey) for v in obj]
    elif hasattr(obj, "__dict__"):
        data = dict([(key, todict(value, classkey))
            for key, value in obj.__dict__.items()
            if not callable(value) and not key.startswith('_')])
        if classkey is not None and hasattr(obj, "__class__"):
            data[classkey] = obj.__class__.__name__
        return data
    else:
        return obj