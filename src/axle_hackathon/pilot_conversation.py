"""Deterministic synthetic conversation; no model extraction or real-data mode."""
from secrets import token_urlsafe

from .pilot import CostItem, Opportunity, Profile


class PilotConversation:
    def __init__(self, inbox):
        self.inbox = inbox
        self._flows = inbox._conversation_states

    def clear(self,user,chat):
        with self.inbox._lock:
            self._flows.pop(self.inbox._carrier(user,chat),None)

    def purge_expired(self):
        """Host maintenance must run alongside inbox expiry cleanup."""
        with self.inbox._lock:
            now = self.inbox._now()
            for carrier, flow in tuple(self._flows.items()):
                access = self.inbox._active.get(carrier)
                if (flow['step']=='memory' and flow['notice'].expires_at <= now
                        or flow['step']!='memory' and
                        (access is None or access.token!=flow['token'] or access.expires_at<=now)):
                    self._flows.pop(carrier,None)

    def handle(self, user, chat, text):
        """Trusted transport calls under inbox lock; callbacks contain an opaque step nonce."""
        with self.inbox._lock:
            carrier = self.inbox._carrier(user, chat)
            if text == '/start':
                self.inbox._clear(carrier)
                notice = self.inbox.disclosure(user, chat)
                self._flows[carrier] = dict(step='memory', nonce=token_urlsafe(12), notice=notice,
                                           values={}, token=None)
                return self._prompt(carrier, notice.text + '\nSynthetic development only. '
                    'Use invented figures. Reply session or remember. Reply only while safely parked.')
            flow = self._flows.get(carrier)
            if flow is None:
                raise ValueError('Start a fresh intake with /start')
            parts = text.split(' ', 2)
            if len(parts) < 2 or parts[1] != flow['nonce']:
                raise ValueError('Stale conversation step')
            if flow['step'] != 'memory':
                try:
                    self.inbox._access(user, chat, flow['token'])
                except PermissionError:
                    self._flows.pop(carrier,None)
                    raise
            command = parts[0]
            value = parts[2] if len(parts) == 3 else ''
            if command == '/save' and flow['step']=='confirmed' and not value:
                saved = self.inbox.save_profile(user,chat,flow['token'],flow['revision'],
                                                expected_version=flow.get('saved_version'))
                flow['saved_version']=saved.version
                flow['nonce']=token_urlsafe(12)
                return self._prompt(carrier,'Profile explicitly saved. New trips still need review and confirmation.')
            if command == '/confirm' and flow['step'] == 'review' and not value:
                self.inbox.confirm(user, chat, flow['token'], flow['revision'])
                flow['nonce'] = token_urlsafe(12)
                flow['step'] = 'confirmed'
                return self._prompt(carrier, 'Confirmed synthetic revision. Use /evaluate, '
                    'or correct a field with /edit. Use /save STEP only if you chose remember. '
                    '/forget withdraws consent.')
            if command == '/edit' and flow['step'] in ('review', 'confirmed'):
                field, new_value = value.split(' ', 1)
                if field not in ('payout','loaded_miles','deadhead_miles','reposition_miles',
                                 'trip_hours','schedule','target','cpm'):
                    raise ValueError('Unsupported correction')
                values = dict(flow['values'])
                values[field] = self._unknown(new_value)
                return self._review(user, chat, carrier, values)
            if command != '/reply':
                raise ValueError('Unexpected conversation command')
            values = dict(flow['values'])
            step = flow['step']
            if step == 'memory':
                choices = {'session':'session_only', 'remember':'remember_profile'}
                if value not in choices:
                    raise ValueError('Choose session or remember')
                access = self.inbox.consent(user, chat, flow['notice'].token, choices[value])
                flow['token'] = access.token
                # Consent clears previous state; retain only this newly acknowledged flow.
                self._flows[carrier] = flow
                if value=='remember':
                    saved=self.inbox.load_profile(user,chat,access.token)
                    flow['saved_version']=saved.version if saved else None
                return self._advance(carrier, 'equipment', values,
                    'Which unit will do the trip? Enter equipment label and owned/financed/rented '
                    '(example: box_truck_26ft owned). Unknown/Skip pauses intake; Update restarts this question.')
            if value.lower() in ('unknown','skip','update') and step == 'equipment':
                return self._advance(carrier, step, values,
                    'Equipment is needed to create a profile. Enter equipment label and arrangement, '
                    'or /forget to stop. No costs or capabilities will be assumed.')
            if step == 'equipment':
                equipment, arrangement = value.split(' ', 1)
                Profile(equipment=equipment, arrangement=arrangement, mode='itemized', source='synthetic supplied')
                values.update(equipment=equipment, arrangement=arrangement)
                if arrangement == 'rented':
                    return self._advance(carrier, 'coverage', values,
                        'Does the rental mileage charge cover maintenance? Reply yes/no/unknown.')
                return self._advance(carrier,'trip',values,
                    'Enter complete payout, loaded miles, and your deadhead miles, separated by spaces. '
                    'Example: 420 180 40. Deadhead may be unknown; payout excludes no unconfirmed extras.')
            if step == 'coverage':
                if value not in ('yes','no','unknown','skip'):
                    raise ValueError('Choose yes/no/unknown')
                values['coverage'] = {'yes':True,'no':False,'unknown':None,'skip':None}[value]
                return self._advance(carrier,'trip',values,
                    'Enter complete payout, loaded miles, and your deadhead miles. Unknown deadhead is allowed.')
            if step == 'trip':
                payout, loaded, deadhead = value.split()
                values.update(payout=payout,loaded_miles=loaded,deadhead_miles=self._unknown(deadhead))
                self._models(values)  # Validate supplied numbers before advancing.
                return self._advance(carrier,'timing',values,
                    'Enter reposition miles, total trip hours including dwell, and schedule '
                    'feasible/conflict/unknown. Example: 20 6 feasible. Unknown/Skip is allowed '
                    'for miles or hours. Feasible is your assertion, not an HOS check.')
            if step == 'timing':
                reposition, hours, schedule = value.split()
                values.update(reposition_miles=self._unknown(reposition),trip_hours=self._unknown(hours),
                              schedule='unknown' if schedule=='skip' else schedule)
                self._models(values)
                return self._advance(carrier,'target',values,
                    'What is your all-operating-mile revenue target? Enter dollars/mile or Unknown/Skip.')
            if step == 'target':
                values['target'] = self._unknown(value)
                self._models(values)
                return self._advance(carrier,'costs',values,
                    'Enter a planning cost per ALL operating miles only if it includes fuel, labor '
                    '(including owner labor), insurance, truck/rental base and mileage, maintenance, '
                    'tolls, miscellaneous and contingency. Nothing will be added. Otherwise Unknown/Skip. '
                    'This first intake flow cannot itemize costs; unknown costs limit the recommendation.')
            if step == 'costs':
                values['cpm'] = self._unknown(value)
                return self._review(user,chat,carrier,values)
            raise ValueError('Unexpected conversation step')

    @staticmethod
    def _unknown(value):
        return None if value.lower() in ('unknown','skip') else value

    @staticmethod
    def _models(values):
        cpm = values.get('cpm')
        profile = Profile(equipment=values['equipment'],arrangement=values['arrangement'],
            mode='itemized' if cpm is None else 'all_in_cpm',cpm=cpm,
            cpm_includes=() if cpm is None else tuple(CostItem.model_fields['name'].annotation.__args__),
            maintenance_covered_by_rental=values.get('coverage'),
            target_all_mile_rpm=values.get('target'),source='synthetic Telegram supplied draft')
        opportunity = None
        if 'payout' in values:
            opportunity = Opportunity(payout=values['payout'],loaded_miles=values['loaded_miles'],
                deadhead_miles=values.get('deadhead_miles'),reposition_miles=values.get('reposition_miles'),
                trip_hours=values.get('trip_hours'),schedule=values.get('schedule','unknown'),
                origin='synthetic',operation='hypothetical',scope='Synthetic intake; supplied timing assertion',
                source='invented Telegram development inputs')
        return profile, opportunity

    def _review(self,user,chat,carrier,values):
        flow = self._flows[carrier]
        profile, opportunity = self._models(values)
        snapshot = self.inbox.put(user,chat,flow['token'],profile,opportunity,
                                  expected_revision=flow.get('revision',0))
        flow['revision'] = snapshot.revision
        self._advance(carrier,'review',values,'')
        details = '\n'.join(f'{key}: {value if value is not None else "unknown"}'
                            for key,value in values.items())
        return self._prompt(carrier, f'SYNTHETIC DRAFT revision {snapshot.revision}\n{details}\n'
            'CPM, if supplied, includes every listed category on all operating miles. '
            'Amounts are planning inputs, not accounting profit. Review every fact. '
            'Use /confirm NONCE to confirm, or /edit NONCE field value to correct. '
            'Edits require fresh confirmation; Unknown/Skip preserves an unknown.')

    def _advance(self,carrier,step,values,prompt):
        self._flows[carrier].update(step=step,values=values,nonce=token_urlsafe(12))
        return self._prompt(carrier,prompt)

    def _prompt(self,carrier,prompt):
        return prompt + '\nStep: ' + self._flows[carrier]['nonce'] + '\nReply format: /reply STEP answer'
