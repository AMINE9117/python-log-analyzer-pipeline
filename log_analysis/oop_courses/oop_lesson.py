if __name__ == "__main__":
    """
    polymorphiseme : len la fonction polymorphe
    -meme nom mais pas la meme implementation dans les sous classes
    -classe mere object(abstract) et les sous classes str,list,tuple,set
    -len in object not defined
    """
    l:list[object]=[1234,[],('a','b'),{1,2,3}]
    sum:int=0
    for e in l :
        if isinstance(e,str):
            sum = sum + len(e)
        if isinstance(e,tuple):
            sum = sum + len(e)
        if isinstance(e,set):
            sum = sum + len(e)

    print(sum)