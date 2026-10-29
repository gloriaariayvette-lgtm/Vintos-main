"""Small CPU selective diagonal scan; independent of live organs."""
import numpy as np
import torch
from torch import nn


class SelectiveScan(nn.Module):
    def __init__(self,width,hidden=24):
        super().__init__()
        self.hidden=hidden
        self.proposal=nn.Linear(width,hidden)
        self.select=nn.Linear(width,hidden)
        self.clock=nn.Linear(width,hidden)
        self.register_buffer('taus',torch.logspace(np.log10(300),np.log10(604800),hidden))
        self.emotion=nn.Linear(width+hidden,77)
        self.source=nn.Linear(hidden,12)
        self.gap=nn.Linear(hidden,1)
        self.text=nn.Linear(hidden,32)
        nn.init.zeros_(self.emotion.weight);nn.init.zeros_(self.emotion.bias)
        nn.init.zeros_(self.text.weight);nn.init.zeros_(self.text.bias)

    def forward(self,x,dt,state=None,reset=False):
        proposal=torch.tanh(self.proposal(x))
        select=torch.sigmoid(self.select(x))
        rates=.25+3.75*torch.sigmoid(self.clock(x))
        decay=torch.exp(-dt.clamp_min(1)[:,None]*rates/self.taus)
        state=x.new_zeros(self.hidden) if state is None else state
        outputs=[]
        for i in range(len(x)):
            if reset:state=state*0
            state=decay[i]*state+(1-decay[i])*proposal[i]*select[i]
            outputs.append(state)
        return torch.stack(outputs),state


def states(model,x,dt,reset=False):
    model.eval();rows=[];h=None
    with torch.no_grad():
        for start in range(0,len(x),128):
            out,h=model(torch.from_numpy(x[start:start+128]),torch.from_numpy(dt[start:start+128]),h,reset)
            rows.append(out.numpy())
    return np.concatenate(rows)
