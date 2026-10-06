"""Undo/redo history for the main story page; pure data, no Tk."""
import copy


class EditHistory:
    def __init__(self,limit=30):
        self.limit=limit;self.undo_stack=[];self.redo_stack=[]

    def __len__(self):return len(self.undo_stack)

    def __eq__(self,other):
        return isinstance(other,EditHistory) and (self.undo_stack,self.redo_stack)==(other.undo_stack,other.redo_stack)

    @property
    def can_undo(self):return bool(self.undo_stack)

    @property
    def can_redo(self):return bool(self.redo_stack)

    @property
    def undo_label(self):return self.undo_stack[-1][0] if self.undo_stack else None

    @property
    def redo_label(self):return self.redo_stack[-1][0] if self.redo_stack else None

    def record(self,before,after,label):
        """Store `before` for one completed edit; unchanged edits leave history and redo intact."""
        if before==after:return False
        self.undo_stack.append((label,copy.deepcopy(before)));del self.undo_stack[:-self.limit]
        self.redo_stack.clear();return True

    def undo(self,current):
        if not self.undo_stack:raise ValueError('没有可撤销的操作。')
        label,project=self.undo_stack.pop();self.redo_stack.append((label,copy.deepcopy(current)))
        return copy.deepcopy(project),label

    def redo(self,current):
        if not self.redo_stack:raise ValueError('没有可重做的操作。')
        label,project=self.redo_stack.pop();self.undo_stack.append((label,copy.deepcopy(current)))
        return copy.deepcopy(project),label

    def clear(self):self.undo_stack.clear();self.redo_stack.clear()
