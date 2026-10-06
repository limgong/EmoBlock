"""Atomic musical edits, content-based saving, and monotonic async identity."""
import copy

import curve_project as model


class ProjectSession:
    def __init__(self, project):
        model.validate(project)
        self._project = copy.deepcopy(project)
        self._undo = []
        self._redo = []
        self._saved = None
        self._revision = 0
        self._session_id = model.uid()
        self._requests = {}

    @property
    def project(self):
        return copy.deepcopy(self._project)

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    @property
    def is_saved(self):
        return self._saved == model.fingerprint(self._project)

    def mark_saved(self):
        # Caller invokes only after successful durable store.save.
        self._saved = model.fingerprint(self._project)

    def _changed(self):
        self._revision += 1
        self._requests.clear()

    def edit(self, action, **args):
        result = model.edit(self._project, action, **args)
        if result == self._project:
            return False
        self._undo.append(self._project)
        self._undo = self._undo[-30:]
        self._redo.clear()
        self._project = result
        self._changed()
        return True

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._project)
        self._project = self._undo.pop()
        self._changed()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._project)
        self._project = self._redo.pop()
        self._changed()
        return True

    def capture(self, request_id=None):
        request_id = model.uid() if request_id is None else request_id
        model.ident(request_id)
        if request_id in self._requests:
            raise model.ProjectError('DUPLICATE_REQUEST', '该请求已经开始，请等待结果。')
        token = dict(project_id=self._project['project_id'], session_id=self._session_id, request_id=request_id,
            snapshot_id=model.uid(), spec_rev=model.SPEC_REV, contract_rev=model.CONTRACT_REV,
            edit_revision=self._revision, input_fingerprint=model.fingerprint(self._project))
        self._requests[request_id] = copy.deepcopy(token)
        return dict(token=copy.deepcopy(token), project=self.project)

    def accepts(self, token):
        if not isinstance(token, dict):
            return False
        return (self._requests.get(token.get('request_id')) == token
            and token.get('edit_revision') == self._revision
            and token.get('input_fingerprint') == model.fingerprint(self._project))

    def finish(self, token):
        if not self.accepts(token):
            return False
        del self._requests[token['request_id']]
        return True


    def commit(self, project, token=None):
        """Append a prepared material batch; never an arbitrary editor replacement."""
        if token is not None and not self.accepts(token):
            return False
        model.validate(project)
        before = self._project
        allowed = {'sources', 'materials', 'label_counters', 'records', 'contract_rev'}
        if any(before[k] != project[k] for k in before if k not in allowed):
            raise model.ProjectError('PROTECTION_CONFLICT', '批次只能添加素材，不能改变作品或保护。')
        for key in ('sources', 'materials'):
            if project[key][:len(before[key])] != before[key]:
                raise model.ProjectError('PROTECTION_CONFLICT', '不能覆盖或删除已有来源和素材。')
        if project['contract_rev'] not in (before['contract_rev'], model.CONTRACT_REV):
            raise model.ProjectError('UNSUPPORTED_VERSION', '批次契约版本不受支持。')
        changed = any(project[k] != before[k] for k in ('sources', 'materials', 'label_counters'))
        expected = copy.deepcopy(before)
        if changed:
            model.invalidate_records(expected, before)
        if project['records'] != expected['records']:
            raise model.ProjectError('PLAN_VERSION_MISMATCH', '批次不能伪造或改变计划结果。')
        if not changed:
            if token is not None:
                self.finish(token)
            return False
        self._undo.append(before)
        self._undo = self._undo[-30:]
        self._redo.clear()
        self._project = copy.deepcopy(project)
        self._changed()
        return True
