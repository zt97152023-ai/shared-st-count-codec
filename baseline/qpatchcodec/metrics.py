"""Direct realized Bernoulli rate difference under fixed causal contexts."""
import math
from numba import njit
import model

@njit(cache=True)
def nll_delta(ptr,idx,val,graph,old,new):
    total=0.;correction=0.
    for row in range(len(ptr)-1):
        for j in range(ptr[row],ptr[row+1]):
            gene=idx[j];c=model.context(ptr,idx,val,graph,row,gene)
            a=int(old[gene,c]);b=int(new[gene,c])
            if val[j]!=1:a=4096-a;b=4096-b
            term=math.log2(a/b)-correction
            updated=total+term;correction=(updated-total)-term;total=updated
    return total
