"""
since python 3.5
-lisibilite du code
-type check in IDE vscode
"""
b:bool=True
i:int=10
pi:float=22/7
adn:str="AAAAAAADDDDDDDBBBBBBCCCCC"

l:list[str]=["a","b"]
t:tuple[int,...]=(3,4,)
d:dict[str,float]={"fes":20.5,"1":3}

#create new type
Vector=list[float]
v:Vector=[3,4,5.1]
from typing import (
    Any,
    Final,
    Optional,
    Union
)
var:Any=[]
MAX:Final[int]=100
opt:Optional[str]=''
val:Union[list[int],str]=[]