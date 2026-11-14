"""Original compact single-input 1D segmentation network. MIT; no pretrained code."""
import torch
from torch import nn
from torch.nn import functional as F

class Block(nn.Module):
    def __init__(self,cin,cout,dilation=1):
        super().__init__()
        self.net=nn.Sequential(nn.Conv1d(cin,cout,7,padding=3*dilation,dilation=dilation,bias=False),
            nn.GroupNorm(4,cout),nn.SiLU(),nn.Conv1d(cout,cout,5,padding=2,bias=False),nn.GroupNorm(4,cout),nn.SiLU())
    def forward(self,x):return self.net(x)

class CompactSegmenter(nn.Module):
    def __init__(self):
        super().__init__()
        self.e0=Block(1,8);self.e1=Block(8,16);self.e2=Block(16,32);self.b=Block(32,64,4)
        self.d2=Block(96,32);self.d1=Block(48,16);self.d0=Block(24,8);self.out=nn.Conv1d(8,4,1)
    def forward(self,x):
        a=self.e0(x);b=self.e1(F.max_pool1d(a,2));c=self.e2(F.max_pool1d(b,2));d=self.b(F.max_pool1d(c,2))
        d=self.d2(torch.cat((F.interpolate(d,size=c.shape[-1],mode='linear',align_corners=False),c),1))
        d=self.d1(torch.cat((F.interpolate(d,size=b.shape[-1],mode='linear',align_corners=False),b),1))
        d=self.d0(torch.cat((F.interpolate(d,size=a.shape[-1],mode='linear',align_corners=False),a),1))
        return self.out(d)
