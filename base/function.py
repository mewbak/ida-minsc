"""
Function module

This module exposes a number of tools that can be used on or in
a particular function. There are a couple of namespaces that can allow
one to interact with the different components that are available for
a function.

The base argument type for a number of the utilities within this module
is the ``idaapi.func_t``. This type is interchangeable with an address or
a name and either can be used to identify a function. Some of the tools
exposed in this module allow for one to modify comments, rename, or
determine the relationships between functions.

Some namespaces are provided for interacting with the different components
that IDA associates with each function. This can be used to navigate
to the different parts of a function. Some of the available namespaces
are ``type``, ``block``, ``chunk``, ``blocks``, ``chunks``, and ``frame``.
"""

import six
from six.moves import builtins

import functools, operator, itertools, types
import logging

import database, instruction, structure
import ui, internal
from internal import utils, interface, exceptions as E

import idaapi

## searching
@utils.multicase()
def by_address():
    '''Return the function at the current address.'''
    return by_address(ui.current.address())
@utils.multicase(ea=six.integer_types)
def by_address(ea):
    '''Return the function containing the address `ea`.'''
    ea = interface.address.within(ea)
    res = idaapi.get_func(ea)
    if res is None:
        raise E.FunctionNotFoundError("{:s}.by_address({:#x}) : Unable to locate function.".format(__name__, ea))
    return res
byAddress = utils.alias(by_address)

def by_name(name):
    '''Return the function with the specified `name`.'''
    # convert the name into something friendly for IDA
    res = interface.string.to(name)

    # ask IDA to get its address
    ea = idaapi.get_name_ea(idaapi.BADADDR, res)
    if ea == idaapi.BADADDR:
        raise E.FunctionNotFoundError("{:s}.by_name({!r}) : Unable to locate function by name.".format(__name__, name))

    # now that we have its address, return the func_t
    res = idaapi.get_func(ea)
    if res is None:
        raise E.FunctionNotFoundError("{:s}.by_name({!r}) : Unable to locate function by address.".format(__name__, name))
    return res
byName = utils.alias(by_name)

@utils.multicase()
def by():
    '''Return the current function.'''
    return by_address(ui.current.address())
@utils.multicase(func=idaapi.func_t)
def by(func):
    '''Return the function identified by `func`.'''
    return func
@utils.multicase(ea=six.integer_types)
def by(ea):
    '''Return the function at the address `ea`.'''
    return by_address(ea)
@utils.multicase(name=basestring)
def by(name):
    '''Return the function with the specified `name`.'''
    return by_name(name)

# FIXME: implement a matcher class for func_t

@utils.multicase()
def offset():
    '''Return the offset of the current function from the base of the database.'''
    ea = address()
    return database.getoffset(ea)
@utils.multicase()
def offset(func):
    '''Return the offset of the function `func` from the base of the database.'''
    ea = address(func)
    return database.getoffset(ea)

## properties
@utils.multicase()
def comment(**repeatable):
    '''Return the comment for the current function.'''
    fn = ui.current.function()
    res = idaapi.get_func_cmt(fn, repeatable.get('repeatable', True))
    return interface.string.of(res)
@utils.multicase()
def comment(func, **repeatable):
    """Return the comment for the function `func`.

    If the bool `repeatable` is specified, then return the repeatable comment.
    """
    fn = by(func)
    res = idaapi.get_func_cmt(fn, repeatable.get('repeatable', True))
    return interface.string.of(res)
@utils.multicase(string=basestring)
def comment(string, **repeatable):
    '''Set the comment for the current function to `string`.'''
    fn = ui.current.function()
    return comment(fn, string, **repeatable)
@utils.multicase(string=basestring)
def comment(func, string, **repeatable):
    """Set the comment for the function `func` to `string`.

    If the bool `repeatable` is specified, then modify the repeatable comment.
    """
    fn = by(func)

    res, ok = comment(fn, **repeatable), idaapi.set_func_cmt(fn, interface.string.to(string), repeatable.get('repeatable', True))
    if not ok:
        raise E.DisassemblerError("{:s}.comment({:#x}, {!r}{:s}) : Unable to call idaapi.set_func_cmt({:#x}, {!r}, {!s}).".format(__name__, ea, string, ", {:s}".format(', '.join("{:s}={!r}".format(key, value) for key, value in six.iteritems(repeatable))) if repeatable else '', ea, string, repeatable.get('repeatable', True)))
    return res

@utils.multicase()
def name():
    '''Return the name of the current function.'''
    return name(ui.current.address())
@utils.multicase()
def name(func):
    '''Return the name of the function `func`.'''
    get_name = functools.partial(idaapi.get_name, idaapi.BADADDR) if idaapi.__version__ < 7.0 else idaapi.get_name

    # check to see if it's a runtime-linked function
    rt, ea = interface.addressOfRuntimeOrStatic(func)
    if rt:
        name = get_name(ea)

        # decode the string from IDA's UTF-8
        # XXX: how does demangling work with unicode? this would be implementation specific, no?
        res = interface.string.of(res)

        # demangle it if necessary
        return internal.declaration.demangle(res) if internal.declaration.mangledQ(res) else res
        #return internal.declaration.extract.fullname(internal.declaration.demangle(res)) if internal.declaration.mangledQ(res) else res

    # otherwise it's a regular function, so try and get its name in a couple of ways
    name = idaapi.get_func_name(ea)
    if not name: name = get_name(ea)
    if not name: name = idaapi.get_true_name(ea, ea) if idaapi.__version__ < 6.8 else idaapi.get_ea_name(ea, idaapi.GN_VISIBLE)

    # decode the string from IDA's UTF-8
    # XXX: how does demangling work with unicode? this would be implementation specific, no?
    res = interface.string.of(name)

    # demangle it if we need to
    return internal.declaration.demangle(res) if internal.declaration.mangledQ(res) else res
    #return internal.declaration.extract.fullname(internal.declaration.demangle(res)) if internal.declaration.mangledQ(res) else res
    #return internal.declaration.extract.name(internal.declaration.demangle(res)) if internal.declaration.mangledQ(res) else res
@utils.multicase(none=types.NoneType)
def name(none):
    '''Remove the custom-name from the current function.'''
    # we use ui.current.address() instead of ui.current.function()
    # in case the user might be hovering over an import table
    # function and wanting to rename that instead.
    return name(ui.current.address(), none or '')
@utils.multicase(string=basestring)
def name(string, *suffix):
    '''Set the name of the current function to `string`.'''
    return name(ui.current.address(), string, *suffix)
@utils.multicase(none=types.NoneType)
def name(func, none):
    '''Remove the custom-name from the function `func`.'''
    return name(func, none or '')
@utils.multicase(string=basestring)
def name(func, string, *suffix):
    '''Set the name of the function `func` to `string`.'''

    # combine name with its suffix
    res = (string,) + suffix
    string = interface.tuplename(*res)

    # figure out if address is a runtime or static function
    rt, ea = interface.addressOfRuntimeOrStatic(func)

    # now we can assign the name depending on whether it's a function or a runtime-linked function
    # FIXME: mangle the name and shuffle it into the prototype if possible
    if rt:
        res = database.name(ea, string)
    else:
        res = database.name(ea, string, flags=idaapi.SN_PUBLIC)
    return res

@utils.multicase()
def convention():
    '''Return the calling convention of the current function.'''
    # use ui.current.address() instead of ui.current.function() to deal with import table entries
    return convention(ui.current.address())
@utils.multicase()
def convention(func):
    """Return the calling convention of the function `func`.

    The integer returned corresponds to one of the ``idaapi.CM_CC_*`` constants.
    """
    rt, ea = interface.addressOfRuntimeOrStatic(func)
    sup = internal.netnode.sup.get(ea, 0x3000)
    if sup is None:
        raise E.MissingTypeOrAttribute("{:s}.convention({!r}) : Specified function does not contain a prototype declaration.".format(__name__, func))
    try:
        _, _, cc = interface.node.sup_functype(sup)
    except E.UnsupportedCapability:
        raise E.UnsupportedCapability("{:s}.convention({!r}) : Specified prototype declaration is a type forward which is currently unimplemented.".format(__name__, func))
    return cc
cc = utils.alias(convention)

@utils.multicase()
def prototype():
    '''Return the prototype of the current function if it has one.'''
    # use ui.current.address() instead of ui.current.function() to deal with import table entries
    return prototype(ui.current.address())
@utils.multicase()
def prototype(func):
    '''Return the prototype of the function `func` if it has one.'''
    rt, ea = interface.addressOfRuntimeOrStatic(func)
    funcname = database.name(ea) or name(ea)
    try:
        decl = internal.declaration.function(ea)
        idx = decl.find('(')
        res = "{return:s} {name:s}{parameters:s}".format(result=decl[:idx], name=funcname, parameters=decl[idx:])

    except E.MissingTypeOrAttribute:
        if not internal.declaration.mangledQ(funcname):
            raise
        return internal.declaration.demangle(funcname)
    return res

@utils.multicase()
def bounds():
    '''Return a tuple containing the bounds of the first chunk of the current function.'''
    return range(ui.current.function())
@utils.multicase()
def bounds(func):
    '''Return a tuple containing the bounds of the first chunk of the function `func`.'''
    fn = by(func)
    if fn is None:
        raise E.FunctionNotFoundError("{:s}.bounds({!r}) : Unable to find function at the given location.".format(__name__, func, ea))
    return fn.startEA, fn.endEA
range = utils.alias(bounds)

@utils.multicase()
def color():
    '''Return the color of the current function.'''
    return color(ui.current.function())
@utils.multicase()
def color(func):
    '''Return the color of the function `func`.'''
    fn = by(func)
    b, r = (fn.color&0xff0000)>>16, fn.color&0x0000ff
    return None if fn.color == 0xffffffff else (r<<16) | (fn.color&0x00ff00) | b
@utils.multicase(none=types.NoneType)
def color(func, none):
    '''Remove the color for the function `func`.'''
    fn = by(func)
    fn.color = 0xffffffff
    return bool(idaapi.update_func(fn))
@utils.multicase(rgb=six.integer_types)
def color(func, rgb):
    '''Set the color of the function `func` to `rgb`.'''
    r, b = (rgb&0xff0000)>>16, rgb&0x0000ff
    fn = by(func)
    fn.color = (b<<16) | (rgb&0x00ff00) | r
    return bool(idaapi.update_func(fn))
@utils.multicase(none=types.NoneType)
def color(none):
    '''Remove the color for the current function.'''
    return color(ui.current.function(), None)

@utils.multicase()
def address():
    '''Return the entry-point of the current function.'''
    res = ui.current.function()
    if res is None:
        raise E.FunctionNotFoundError("{:s}.address({:#x}) : Unable to locate the current function.".format(__name__, ui.current.address()))
    return res.startEA
@utils.multicase()
def address(func):
    '''Return the entry-point of the function identified by `func`.'''
    res = by(func)
    return res.startEA
top = addr = utils.alias(address)

@utils.multicase()
def bottom():
    '''Return the exit-points of the current function.'''
    return bottom(ui.current.function())
@utils.multicase()
def bottom(func):
    '''Return the exit-points of the function `func`.'''
    fn = by(func)
    fc = idaapi.FlowChart(f=fn, flags=idaapi.FC_PREDS)
    exit_types = (
        interface.fc_block_type_t.fcb_ret,
        interface.fc_block_type_t.fcb_cndret,
        interface.fc_block_type_t.fcb_noret,
        interface.fc_block_type_t.fcb_enoret,
        interface.fc_block_type_t.fcb_error
    )
    return tuple(database.address.prev(n.endEA) for n in fc if n.type in exit_types)

@utils.multicase()
def marks():
    '''Return all the marks in the current function.'''
    return marks(ui.current.function())
@utils.multicase()
def marks(func):
    '''Return all the marks in the function `func`.'''
    fn, res = by(func), []
    for ea, comment in database.marks():
        try:
            if address(ea) == fn.startEA:
                res.append((ea, comment))
        except E.FunctionNotFoundError:
            pass
        continue
    return res

## functions
@utils.multicase()
def new():
    '''Make a function at the current address.'''
    return new(ui.current.address())
@utils.multicase(start=six.integer_types)
def new(start, **end):
    """Make a function at the address `start` and return its entrypoint.

    If the address `end` is specified, then stop processing the function at its address.
    """
    start = interface.address.inside(start)
    end = end.get('end', idaapi.BADADDR)
    ok = idaapi.add_func(start, end)
    ui.state.wait()
    return address(start) if ok else None
make = add = utils.alias(new)

@utils.multicase()
def remove():
    '''Remove the definition of the current function from the database.'''
    return remove(ui.current.function())
@utils.multicase()
def remove(func):
    '''Remove the definition of the function `func` from the database.'''
    fn = by(func)
    return idaapi.del_func(fn.startEA)

## chunks
class chunks(object):
    """
    This namespace is for interacting with the different chunks
    associated with a function. By default this namespace will yield
    the boundaries of each chunk associated with a function.

    Some of the ways to use this namespace are::

        > for l, r in function.chunks(): ...
        > for ea in function.chunks.iterate(ea): ...

    """
    @utils.multicase()
    def __new__(cls):
        '''Yield the bounds of each chunk within current function.'''
        return cls(ui.current.function())
    @utils.multicase()
    def __new__(cls, func):
        '''Yield the bounds of each chunk for the function `func`.'''
        fn = by(func)
        fci = idaapi.func_tail_iterator_t(fn, fn.startEA)
        if not fci.main():
            raise E.DisassemblerError("{:s}.chunks({:#x}) : Unable to create an idaapi.func_tail_iterator_t.".format(__name__, fn.startEA))

        while True:
            ch = fci.chunk()
            yield interface.bounds_t(ch.startEA, ch.endEA)
            if not fci.next(): break
        return

    @utils.multicase()
    @classmethod
    def iterate(cls):
        '''Iterate through all the instructions for each chunk in the current function.'''
        return cls.iterate(ui.current.function())
    @utils.multicase()
    @classmethod
    def iterate(cls, func):
        '''Iterate through all the instructions for each chunk in the function `func`.'''
        for start, end in cls(func):
            for ea in itertools.ifilter(database.type.is_code, database.address.iterate(start, end)):
                yield ea
            continue
        return

    @utils.multicase()
    @classmethod
    def at(cls):
        '''Return a tuple containing the bounds of the current function chunk.'''
        return cls.at(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, ea):
        '''Return a tuple containing the bounds of the function chunk at the address `ea`.'''
        fn = by_address(ea)
        return cls.at(fn, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, func, ea):
        '''Return a tuple containing the bounds of the function chunk belonging to `func` at the address `ea`.'''
        fn = by(func)
        for left, right in cls(fn):
            if left <= ea < right:
                return interface.bounds_t(left, right)
            continue
        raise E.AddressNotFoundError("{:s}.at({:#x}, {:#x}) : Unable to locate chunk for address {:#x} in function {:#x}.".format('.'.join((__name__, cls.__name__)), fn.startEA, ea, ea, fn.startEA))

    @utils.multicase(reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, reg, *regs, **modifiers):
        '''Yield each `(address, opnum, state)` within the current function that uses `reg` or any one of the registers in `regs`.'''
        return cls.register(ui.current.function(), reg, *regs, **modifiers)
    @utils.multicase(reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, func, reg, *regs, **modifiers):
        """Yield each `(address, opnum, state)` within the function `func` that uses `reg` or any one of the registers in `regs`.

        If the keyword `write` is True, then only return the result if it's writing to the register.
        """
        iterops = interface.regmatch.modifier(**modifiers)
        uses_register = interface.regmatch.use( (reg,) + regs )

        for ea in cls.iterate(func):
            for opnum in itertools.ifilter(functools.partial(uses_register, ea), iterops(ea)):
                yield ea, opnum, instruction.op_state(ea, opnum)
            continue
        return

iterate = utils.alias(chunks.iterate, 'chunks')
register = utils.alias(chunks.register, 'chunks')

class chunk(object):
    """
    This namespace is for interacting with a specific chunk belonging
    to a function. By default this namespace will return the bounds of
    the chunk containing the requested address.

    The functions in this namespace can be used as::

        > l, r = function.chunk(ea)
        > ea = function.chunk.top()
        > function.chunk.add(function.by(), 0x401000, 0x402000)
        > function.chunk.remove(ea)

    """
    @utils.multicase()
    def __new__(cls):
        '''Return a tuple containing the bounds of the function chunk at the current address.'''
        return chunks.at(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    def __new__(cls, ea):
        '''Return a tuple containing the bounds of the function chunk at the address `ea`.'''
        return chunks.at(ea)

    @utils.multicase()
    @classmethod
    def iterate(cls):
        '''Iterate through all the instructions for the function chunk containing the current address.'''
        for ea in cls.iterate(ui.current.address()):
            yield ea
        return
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def iterate(cls, ea):
        '''Iterate through all the instructions for the function chunk containing the address ``ea``.'''
        start, end = cls(ea)
        for ea in itertools.ifilter(database.type.is_code, database.address.iterate(start, end)):
            yield ea
        return

    @utils.multicase()
    @classmethod
    def at(cls):
        '''Return a tuple containing the bounds of the current function chunk.'''
        return cls.at(ui.current.function(), ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, ea):
        '''Return a tuple containing the bounds of the function chunk at the address `ea`.'''
        fn = by_address(ea)
        return cls.at(fn, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, func, ea):
        '''Return a tuple containing the bounds of the function chunk belonging to `func` at the address `ea`.'''
        return chunks.at(func, ea)

    @utils.multicase()
    @classmethod
    def top(cls):
        '''Return the top address of the chunk at the current address.'''
        left, _ = cls()
        return left
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def top(cls, ea):
        '''Return the top address of the chunk at address `ea`.'''
        left, _ = cls(ea)
        return left
    @utils.multicase()
    @classmethod
    def bottom(cls):
        '''Return the bottom address of the chunk at the current address.'''
        _, right = cls()
        return right
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def bottom(cls, ea):
        '''Return the bottom address of the chunk at address `ea`.'''
        _, right = cls(ea)
        return right

    @utils.multicase(start=six.integer_types, end=six.integer_types)
    @classmethod
    def add(cls, start, end):
        '''Add the chunk `start` to `end` to the current function.'''
        return cls.add(ui.current.function(), start, end)
    @utils.multicase(start=six.integer_types, end=six.integer_types)
    @classmethod
    def add(cls, func, start, end):
        '''Add the chunk `start` to `end` to the function `func`.'''
        fn = by(func)
        start, end = interface.address.inside(start, end)
        return idaapi.append_func_tail(fn, start, end)

    @utils.multicase()
    @classmethod
    def remove(cls):
        return cls.remove(ui.current.address())

    @utils.multicase(ea=six.integer_types)
    @classmethod
    def remove(cls, ea):
        '''Remove the chunk at `ea` from its function.'''
        return cls.remove(ea, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def remove(cls, func, ea):
        '''Remove the chunk at `ea` from the function `func`.'''
        fn, ea = by(func), interface.address.within(ea)
        return idaapi.remove_func_tail(fn, ea)

    @utils.multicase(ea=six.integer_types)
    @classmethod
    def assign(cls, ea):
        '''Assign the chunk at `ea` to the current function.'''
        return cls.assign_chunk(ui.current.function(), ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def assign(cls, func, ea):
        '''Assign the chunk at `ea` to the function `func`.'''
        fn, ea = by(func), interface.address.within(ea)
        return idaapi.set_tail_owner(fn, ea)
add_chunk, remove_chunk, assign_chunk = utils.alias(chunk.add, 'chunk'), utils.alias(chunk.remove, 'chunk'), utils.alias(chunk.assign, 'chunk')

@utils.multicase()
def within():
    '''Return true if the current address is within a function.'''
    return within(ui.current.address())
@utils.multicase(ea=six.integer_types)
def within(ea):
    '''Return true if the address `ea` is within a function.'''
    ea = interface.address.within(ea)
    return idaapi.get_func(ea) is not None

# Checks if ea is contained in function or in any of its chunks
@utils.multicase()
def contains():
    '''Returns True if the current address is within a function.'''
    return contains(ui.current.function(), ui.current.address())
@utils.multicase(ea=six.integer_types)
def contains(ea):
    '''Returns True if the address `ea` is contained by the current function.'''
    return contains(ui.current.function(), ea)
@utils.multicase(ea=six.integer_types)
def contains(func, ea):
    '''Returns True if the address `ea` is contained by the function `func`.'''
    try:
        fn = by(func)
    except E.FunctionNotFoundError:
        return False
    ea = interface.address.within(ea)
    return any(start <= ea < end for start, end in chunks(fn))

class blocks(object):
    """
    This namespace is for interacting with all of the basic blocks within
    the specified function. By default this namespace will yield the
    boundaries of each basic block defined within the function.

    This namespace provides a small number of utilities that can be
    used to extract the basic blocks of a function and convert them
    into a flow-graph such as ``idaapi.FlowChart``, or a digraph as used
    by the ``networkx`` module.

    Due to ``idaapi.FlowChart`` and networkx's digraph being used so
    often, these functions are exported globally as ``function.flowchart``
    and ``function.digraph``.

    Some examples of this namespace's usage::

        > for bb in function.blocks(): ...
        > chart = function.blocks.flowchart(ea)
        > G = function.blocks.graph()

    """
    @utils.multicase()
    def __new__(cls):
        '''Return the bounds of each basic block for the current function.'''
        return cls(ui.current.function())
    @utils.multicase()
    def __new__(cls, func):
        '''Returns the bounds of each basic block for the function `func`.'''
        for bb in cls.iterate(func):
            yield interface.bounds_t(bb.startEA, bb.endEA)
        return
    @utils.multicase()
    def __new__(cls, left, right):
        '''Returns each basic block contained within the addresses `left` and `right`.'''
        fn = by_address(left)
        (left, _), (_, right) = block(left), block(database.address.prev(right))
        for bb in cls.iterate(fn):
            if (bb.startEA >= left and bb.endEA <= right):
                yield interface.bounds_t(bb.startEA, bb.endEA)
            continue
        return

    @utils.multicase()
    @classmethod
    def iterate(cls):
        '''Return each ``idaapi.BasicBlock`` for the current function.'''
        return cls.iterate(ui.current.function())
    @utils.multicase()
    @classmethod
    def iterate(cls, func):
        '''Returns each ``idaapi.BasicBlock`` for the function `func`.'''
        fn = by(func)
        fc = idaapi.FlowChart(f=fn, flags=idaapi.FC_PREDS)
        for bb in fc:
            yield bb
        return

    @utils.multicase()
    @classmethod
    def at(cls):
        '''Return the ``idaapi.BasicBlock`` at the current address in the current function.'''
        return cls.at(ui.current.function(), ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, ea):
        '''Return the ``idaapi.BasicBlock`` of address `ea` in the current function.'''
        fn = by_address(ea)
        return cls.at(fn, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, func, ea):
        '''Return the ``idaapi.BasicBlock`` in function `func` at address `ea`.'''
        fn = by(func)
        for bb in blocks.iterate(fn):
            if bb.startEA <= ea < bb.endEA:
                return bb
            continue
        raise E.AddressNotFoundError("{:s}.at({:#x}, {:#x}) : Unable to locate idaapi.BasicBlock for address {:#x} in function {:#x}.".format('.'.join((__name__, cls.__name__)), fn.startEA, ea, ea, fn.startEA))

    @utils.multicase()
    @classmethod
    def flowchart(cls):
        '''Return an ``idaapi.FlowChart`` object for the current function.'''
        return cls.flowchart(ui.current.function())
    @utils.multicase()
    @classmethod
    def flowchart(cls, func):
        '''Return an ``idaapi.FlowChart`` object for the function `func`.'''
        fn = by(func)
        return idaapi.FlowChart(f=fn, flags=idaapi.FC_PREDS)

    @utils.multicase()
    @classmethod
    def digraph(cls):
        '''Return a ``networkx.DiGraph`` of the function at the current address.'''
        return cls.digraph(ui.current.function())
    @utils.multicase()
    @classmethod
    def digraph(cls, func):
        """Return a ``networkx.DiGraph`` of the function at the address `ea`.

        Requires the ``networkx`` module in order to build the graph.
        """
        fn = by(func)

        # create digraph
        import networkx
        attrs = tag(fn.startEA)
        attrs.setdefault('__name__', database.name(fn.startEA))
        attrs.setdefault('__address__', fn.startEA)
        attrs.setdefault('__frame__', frame(fn))
        res = networkx.DiGraph(name=name(fn.startEA), **attrs)

        # create entry node
        attrs = database.tag(fn.startEA)
        operator.setitem(attrs, '__name__', name(fn.startEA))
        operator.setitem(attrs, '__address__', fn.startEA)
        operator.setitem(attrs, '__bounds__', block(fn.startEA))
        block.color(fn.startEA) and operator.setitem(attrs, '__color__', block.color(fn.startEA))
        res.add_node(fn.startEA, attrs)

        # create a graph node for each basicblock
        for b, e in cls(fn):
            if b == fn.startEA: continue
            attrs = database.tag(b)
            operator.setitem(attrs, '__name__', database.name(b))
            operator.setitem(attrs, '__address__', b)
            operator.setitem(attrs, '__bounds__', (b, e))
            block.color(b) and operator.setitem(attrs, '__color__', block.color(b))
            res.add_node(b, attrs)

        # for every single block...
        for b in cls.iterate(fn):
            # ...add an edge to its predecessors
            for p in b.preds():
                # FIXME: figure out more attributes to add
                attrs = {}
                operator.setitem(attrs, '__contiguous__', b.startEA == p.endEA)
                res.add_edge(p.startEA, b.startEA, attrs)

            # ...add an edge to its successors
            for s in b.succs():
                # FIXME: figure out more attributes to add
                attrs = {}
                operator.setitem(attrs, '__contiguous__', b.endEA == s.startEA)
                res.add_edge(b.startEA, s.startEA, attrs)
            continue
        return res
    graph = utils.alias(digraph, 'blocks')

    # XXX: Implement .register for filtering blocks
    # XXX: Implement .search for filtering blocks
flowchart = utils.alias(blocks.flowchart, 'blocks')
digraph = graph = utils.alias(blocks.digraph, 'blocks')

class block(object):
    """
    This namespace is for interacting with a single basic block
    belonging to a function. By default the bounds of the selected
    basic block will be returned. This bounds or an address within
    these bounds can then be used in other functions within this
    namespace.

    Some examples of this functionality can be::

        > B = function.block(ea)
        > bid = function.block.id()
        > c = function.block.color(ea, rgb)
        > print function.block.before(ea)
        > for ea in function.block.iterate(): print database.disasm(ea)
        > for ea, op, st in function.block.register('eax', read=1): ...
        > print function.block.read().encode('hex')
        > print function.block.disasm(ea)

    """
    @utils.multicase()
    @classmethod
    def at(cls):
        '''Return the ``idaapi.BasicBlock`` of the current address in the current function.'''
        return cls.at(ui.current.function(), ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, ea):
        '''Return the ``idaapi.BasicBlock`` of address `ea` in the current function.'''
        fn = by_address(ea)
        return cls.at(fn, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def at(cls, func, ea):
        '''Return the ``idaapi.BasicBlock`` of address `ea` in the function `func`.'''
        return blocks.at(func, ea)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def at(cls, bb):
        '''Return the ``idaapi.BasicBlock`` of the basic block `bb`.'''
        return bb
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def at(cls, bounds):
        '''Return the ``idaapi.BasicBlock`` identified by `bounds`.'''
        left, _ = bounds
        return cls.at(left)

    @utils.multicase()
    @classmethod
    def id(cls):
        '''Return the block id of the current address in the current function.'''
        return cls.at(ui.current.function(), ui.current.address()).id
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def id(cls, ea):
        '''Return the block id of address `ea` in the current function.'''
        return cls.at(ea).id
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def id(cls, func, ea):
        '''Return the block id of address `ea` in the function `func`.'''
        return cls.at(func, ea).id
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def id(cls, bb):
        '''Return the block id of the basic block `bb`.'''
        return bb.id
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def id(cls, bounds):
        '''Return the block id of the basic block identified by `bounds`.'''
        return cls.at(bounds).id

    @utils.multicase()
    def __new__(cls):
        '''Returns the boundaries of the current basic block.'''
        return cls(ui.current.function(), ui.current.address())
    @utils.multicase(ea=six.integer_types)
    def __new__(cls, ea):
        '''Returns the boundaries of the basic block at address `ea`.'''
        return cls(by_address(ea), ea)
    @utils.multicase(ea=six.integer_types)
    def __new__(cls, func, ea):
        '''Returns the boundaries of the basic block at address `ea` in function `func`.'''
        res = blocks.at(func, ea)
        return interface.bounds_t(res.startEA, res.endEA)
    @utils.multicase(bb=idaapi.BasicBlock)
    def __new__(cls, bb):
        '''Returns the boundaries of the basic block `bb`.'''
        return interface.bounds_t(bb.startEA, bb.endEA)
    @utils.multicase(bounds=types.TupleType)
    def __new__(cls, bounds):
        '''Return the boundaries of the basic block identified by `bounds`.'''
        left, _ = bounds
        return cls(left)

    @utils.multicase()
    @classmethod
    def top(cls):
        '''Return the top address of the basic block at the current address.'''
        left, _ = cls()
        return left
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def top(cls, ea):
        '''Return the top address of the basic block at address `ea`.'''
        left, _ = cls(ea)
        return left
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def top(cls, bb):
        '''Return the top address of the basic block `bb`.'''
        left, _ = cls(bb)
        return left
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def top(cls, bounds):
        '''Return the top address of the basic block identified by `bounds`.'''
        left, _ = cls(bounds)
        return left

    @utils.multicase()
    @classmethod
    def bottom(cls):
        '''Return the bottom address of the basic block at the current address.'''
        _, right = cls()
        return right
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def bottom(cls, ea):
        '''Return the bottom address of the basic block at address `ea`.'''
        _, right = cls(ea)
        return right
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def bottom(cls, bb):
        '''Return the bottom address of the basic block `bb`.'''
        _, right = cls(bb)
        return right
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def bottom(cls, bounds):
        '''Return the bottom address of the basic block identified by `bounds`.'''
        _, right = cls(bounds)
        return right

    @utils.multicase()
    @classmethod
    def color(cls):
        '''Returns the color of the basic block at the current address.'''
        return cls.color(ui.current.address())
    @utils.multicase(none=types.NoneType)
    @classmethod
    def color(cls, none):
        '''Removes the color of the basic block at the current address.'''
        return cls.color(ui.current.address(), None)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def color(cls, ea):
        '''Returns the color of the basic block at the address `ea`.'''
        bb = cls.at(ea)
        return cls.color(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def color(cls, bb):
        '''Returns the color of the basic block `bb`.'''
        fn, n = by_address(bb.startEA), idaapi.node_info_t()
        ok = idaapi.get_node_info2(n, fn.startEA, bb.id)
        if ok and n.valid_bg_color():
            res = n.bg_color
            b, r = (res&0xff0000)>>16, res&0x0000ff
            return (r<<16) | (res&0x00ff00) | b
        return None
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def color(cls, bounds):
        '''Returns the color of the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.color(bb)
    @utils.multicase(ea=six.integer_types, none=types.NoneType)
    @classmethod
    def color(cls, ea, none):
        '''Removes the color of the basic block at the address `ea`.'''
        res, fn, bb = cls.color(ea), by_address(ea), cls.id(ea)
        try: idaapi.clr_node_info2(fn.startEA, bb, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
        finally: idaapi.refresh_idaview_anyway()

        # clear the color of each item too.
        for ea in block.iterate(ea):
            database.color(ea, None)
            # internal.netnode.alt.remove(ea, 0x14)
        return res
    @utils.multicase(bounds=types.TupleType, none=types.NoneType)
    @classmethod
    def color(cls, bounds, none):
        '''Removes the color of the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.color(bb, None)
    @utils.multicase(bb=idaapi.BasicBlock, none=types.NoneType)
    @classmethod
    def color(cls, bb, none):
        '''Removes the color of the basic block `bb`.'''
        res, fn = cls.color(bb), by_address(bb.startEA)
        try: idaapi.clr_node_info2(fn.startEA, bb.id, idaapi.NIF_BG_COLOR | idaapi.NIF_FRAME_COLOR)
        finally: idaapi.refresh_idaview_anyway()

        # clear the color of each item too.
        for ea in block.iterate(bb):
            database.color(ea, None)
            #internal.netnode.alt.remove(ea, 0x14)
        return res
    @utils.multicase(ea=six.integer_types, rgb=six.integer_types)
    @classmethod
    def color(cls, ea, rgb, **frame):
        """Sets the color of the basic block at the address `ea` to `rgb`.

        If the color `frame` is specified, set the frame to the specified color.
        """
        res, fn, bb = cls.color(ea), by_address(ea), cls.id(ea)
        n = idaapi.node_info_t()

        # specify the bgcolor
        r, b = (rgb&0xff0000) >> 16, rgb&0x0000ff
        n.bg_color = n.frame_color = (b<<16) | (rgb&0x00ff00) | r

        # now the frame color
        frgb = frame.get('frame', 0x000000)
        fr, fb = (frgb&0xff0000)>>16, frgb&0x0000ff
        n.frame_color = (fb<<16) | (frgb&0x00ff00) | fr

        # set the node
        f = (idaapi.NIF_BG_COLOR|idaapi.NIF_FRAME_COLOR) if frame else idaapi.NIF_BG_COLOR
        try: idaapi.set_node_info2(fn.startEA, bb, n, f)
        finally: idaapi.refresh_idaview_anyway()

        # update the color of each item too
        for ea in block.iterate(ea):
            database.color(ea, rgb)
            #internal.netnode.alt.set(ea, 0x14, n.bg_color)
        return res
    @utils.multicase(bb=idaapi.BasicBlock, rgb=six.integer_types)
    @classmethod
    def color(cls, bb, rgb, **frame):
        '''Sets the color of the basic block `bb` to `rgb`.'''
        res, fn, n = cls.color(bb), by_address(bb.startEA), idaapi.node_info_t()

        # specify the bg color
        r, b = (rgb&0xff0000) >> 16, rgb&0x0000ff
        n.bg_color = n.frame_color = (b<<16) | (rgb&0x00ff00) | r

        # now the frame color
        frgb = frame.get('frame', 0x000000)
        fr, fb = (frgb&0xff0000)>>16, frgb&0x0000ff
        n.frame_color = (fb<<16) | (frgb&0x00ff00) | fr

        # set the node
        f = (idaapi.NIF_BG_COLOR|idaapi.NIF_FRAME_COLOR) if frame else idaapi.NIF_BG_COLOR
        try: idaapi.set_node_info2(fn.startEA, bb.id, n, f)
        finally: idaapi.refresh_idaview_anyway()

        # update the colors of each item too.
        for ea in block.iterate(bb):
            database.color(ea, rgb)
            #internal.netnode.alt.set(ea, 0x14, n.bg_color)
        return res
    @utils.multicase(bounds=types.TupleType, rgb=six.integer_types)
    @classmethod
    def color(cls, bounds, rgb, **frame):
        '''Sets the color of the basic block identifed by `bounds` to `rgb`.'''
        bb = cls.at(bounds)
        return cls.color(bb, rgb, **frame)

    @utils.multicase()
    @classmethod
    def before(cls):
        '''Return the addresses of all the instructions that branch to the current basic block.'''
        return cls.before(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def before(cls, ea):
        '''Return the addresses of all the instructions that branch to the basic block at address `ea`.'''
        res = blocks.at(ea)
        return cls.before(res)
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def before(cls, bounds):
        '''Return the addresses of all the instructions that branch to the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.before(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def before(cls, bb):
        '''Return the addresses of all the instructions that branch to the basic block `bb`.'''
        return [database.address.prev(bb.endEA) for bb in bb.preds()]
    predecessors = preds = utils.alias(before, 'block')

    @utils.multicase()
    @classmethod
    def after(cls):
        '''Return the addresses of all the instructions that the current basic block leaves to.'''
        return cls.after(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def after(cls, ea):
        '''Return the addresses of all the instructions that the basic block at address `ea` leaves to.'''
        bb = cls.at(ea)
        return cls.after(bb)
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def after(cls, bounds):
        '''Return the addresses of all the instructions that branch to the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.after(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def after(cls, bb):
        '''Return the addresses of all the instructions that branch to the basic block `bb`.'''
        return [bb.startEA for bb in bb.succs()]
    successors = succs = utils.alias(after, 'block')

    @utils.multicase()
    @classmethod
    def iterate(cls):
        '''Yield all the addresses in the current basic block.'''
        return cls.iterate(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def iterate(cls, ea):
        '''Yield all the addresses in the basic block at address `ea`.'''
        left, right = cls(ea)
        return database.address.iterate(left, right)
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def iterate(cls, bounds):
        '''Yield all the addresses in the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.iterate(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def iterate(cls, bb):
        '''Yield all the addresses in the basic block `bb`.'''
        left, right = bb.startEA, bb.endEA
        return database.address.iterate(left, right)

    @utils.multicase(reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, reg, *regs, **modifiers):
        '''Yield each `(address, opnum, state)` within the current block that uses `reg` or any one of the registers in `regs`.'''
        return cls.register(ui.current.address(), reg, *regs, **modifiers)
    @utils.multicase(ea=six.integer_types, reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, ea, reg, *regs, **modifiers):
        '''Yield each `(address, opnum, state)` within the block containing `ea` that uses `reg` or any one of the registers in `regs`.'''
        blk = blocks.at(ea)
        return cls.register(blk, reg, *regs, **modifiers)
    @utils.multicase(bounds=types.TupleType, reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, bounds, reg, *regs, **modifiers):
        '''Yield each `(address, opnum, state)` within the block identified by `bounds` that uses `reg` or any one of the registers in `regs`.'''
        bb = cls.at(bounds)
        return cls.register(bb, reg, *regs, **modifiers)
    @utils.multicase(bb=idaapi.BasicBlock, reg=(basestring, interface.register_t))
    @classmethod
    def register(cls, bb, reg, *regs, **modifiers):
        """Yield each `(address, opnum, state)` within the block `bb` that uses `reg` or any one of the registers in `regs`.

        If the keyword `write` is true, then only return the result if it's writing to the register.
        """
        iterops = interface.regmatch.modifier(**modifiers)
        uses_register = interface.regmatch.use( (reg,) + regs )

        for ea in cls.iterate(bb):
            for opnum in itertools.ifilter(functools.partial(uses_register, ea), iterops(ea)):
                yield ea, opnum, instruction.op_state(ea, opnum)
            continue
        return

    @utils.multicase()
    @classmethod
    def read(cls):
        '''Return all the bytes contained in the current basic block.'''
        return cls.read(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def read(cls, ea):
        '''Return all the bytes contained in the basic block at address `ea`.'''
        l, r = cls(ea)
        return database.read(l, r - l)
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def read(cls, bounds):
        '''Return all the bytes contained in the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.read(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def read(cls, bb):
        '''Return all the bytes contained in the basic block `bb`.'''
        l, r = cls(bb)
        return database.read(l, r - l)

    @utils.multicase()
    @classmethod
    def disassemble(cls, **options):
        '''Returns the disassembly of the basic block at the current address.'''
        return cls.disassemble(ui.current.address(), **options)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def disassemble(cls, ea, **options):
        '''Returns the disassembly of the basic block at the address `ea`.'''
        F = functools.partial(database.disassemble, **options)
        return '\n'.join(itertools.imap(F, cls.iterate(ea)))
    @utils.multicase(bounds=types.TupleType)
    @classmethod
    def disassemble(cls, bounds, **options):
        '''Returns the disassembly of the basic block identified by `bounds`.'''
        bb = cls.at(bounds)
        return cls.disassemble(bb)
    @utils.multicase(bb=idaapi.BasicBlock)
    @classmethod
    def disassemble(cls, bb, **options):
        '''Returns the disassembly of the basic block `bb`.'''
        F = functools.partial(database.disassemble, **options)
        return '\n'.join(itertools.imap(F, cls.iterate(bb)))
    disasm = utils.alias(disassemble, 'block')

    # FIXME: implement .decompile for an idaapi.BasicBlock type too
    @utils.multicase()
    @classmethod
    def decompile(cls):
        '''(UNSTABLE) Returns the decompiled code of the basic block at the current address.'''
        return cls.decompile(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def decompile(cls, ea):
        '''(UNSTABLE) Returns the decompiled code of the basic block at the address `ea`.'''
        source = idaapi.decompile(ea)

        res = itertools.imap(functools.partial(operator.__getitem__, source.eamap), cls.iterate(ea))
        res = itertools.chain(*res)
        formatted = reduce(lambda t, c: t if t[-1].ea == c.ea else t+[c], res, [next(res)])

        res = []
        # FIXME: This has been pretty damn unstable in my tests.
        try:
            for fmt in formatted:
                res.append( fmt.print1(source.__deref__()) )
        except TypeError: pass
        res = itertools.imap(idaapi.tag_remove, res)
        return '\n'.join(map(interface.string.of, res))

class frame(object):
    """
    This namespace is for getting information about the selected
    function's frame. By default, this namespace will return a
    ``structure_t`` representing the frame belonging to the specified
    function.

    Some ways of using this can be::

        > print function.frame()
        > print hex(function.frame.id(ea))
        > sp = function.frame.delta(ea)

    """
    @utils.multicase()
    def __new__(cls):
        '''Return the frame of the current function.'''
        return cls(ui.current.function())

    @utils.multicase()
    def __new__(cls, func):
        '''Return the frame of the function `func`.'''
        fn = by(func)
        res = idaapi.get_frame(fn.startEA)
        if res is not None:
            return structure.by_identifier(res.id, offset=-fn.frsize)
        raise E.MissingTypeOrAttribute("{:s}({:#x}) : The specified function does not have a frame.".format('.'.join((__name__, cls.__name__)), fn.startEA))

    @utils.multicase()
    @classmethod
    def id(cls):
        '''Returns the structure id for the current function's frame.'''
        return cls.id(ui.current.function())
    @utils.multicase()
    @classmethod
    def id(cls, func):
        '''Returns the structure id for the function `func`.'''
        fn = by(func)
        return fn.frame

    @utils.multicase()
    @classmethod
    def delta(cls):
        '''Returns the stack delta for the current address within its function.'''
        return cls.delta(ui.current.address())
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def delta(cls, ea):
        '''Returns the stack delta for the address `ea` within its given function.'''
        fn, ea = by_address(ea), interface.address.inside(ea)
        return idaapi.get_spd(fn, ea)
    @utils.multicase(ea=six.integer_types)
    @classmethod
    def delta(cls, func, ea):
        '''Returns the stack delta for the address `ea` within the function `func`.'''
        fn, ea = by(func), interface.address.inside(ea)
        return idaapi.get_spd(fn, ea)

    class args(object):
        """
        This namespace is for returning information about the arguments
        within a function's frame. By default, this namespace will yield
        each argument as a tuple containing the `(offset, name, size)`.

        At the moment, register-based calling conventions are not
        supported.

        Some ways of using this are::

            > print function.frame.args(f)
            > print function.frame.args.size(ea)

        """

        @utils.multicase()
        def __new__(cls):
            '''Yield each argument in the current function.'''
            return cls(ui.current.address())
        @utils.multicase()
        def __new__(cls, func):
            """Yield each argument for the function `func` in order.

            Each result is of the format (offset, name, size).
            """
            rt, ea = interface.addressOfRuntimeOrStatic(func)
            if rt:
                target = func
                database.imports.at(target)

                # grab from declaration
                o = 0
                for arg in internal.declaration.arguments(target):
                    sz = internal.declaration.size(arg)
                    yield o, arg, sz
                    o += sz
                return

            # grab the function
            fn = by(ea)

            # now the calling convention
            try:
                cc = convention(ea)
            except E.MissingTypeOrAttribute:
                cc = idaapi.CM_CC_UNKNOWN

            # grab from structure
            fr = idaapi.get_frame(fn)
            if fr is None:  # unable to figure out arguments
                raise E.MissingTypeOrAttribute("{:s}({:#x}) : Unable to get the function frame.".format('.'.join((__name__, cls.__name__)), fn.startEA))

            # FIXME: The calling conventions should be defined within the interface.architecture_t
            if cc not in {idaapi.CM_CC_VOIDARG, idaapi.CM_CC_CDECL, idaapi.CM_CC_ELLIPSIS, idaapi.CM_CC_STDCALL, idaapi.CM_CC_PASCAL}:
                logging.debug("{:s}({:#x}) : Possibility that register-based arguments will not be listed due to non-implemented calling convention. Calling convention is {:#x}.".format('.'.join((__name__, cls.__name__)), fn.startEA, cc))

            base = get_vars_size(fn)+get_regs_size(fn)
            for (off, size), (name, _, _) in structure.fragment(fr.id, base, get_args_size(fn)):
                yield off - base, name, size
            return

        @utils.multicase()
        @classmethod
        def size(cls):
            '''Returns the size of the arguments for the current function.'''
            return cls.size(ui.current.function())
        @utils.multicase()
        @classmethod
        def size(cls, func):
            '''Returns the size of the arguments for the function `func`.'''
            fn = by(func)
            max = structure.size(get_frameid(fn))
            total = get_vars_size(fn) + get_regs_size(fn)
            return max - total
    arguments = args    # XXX: ns alias

    class lvars(object):
        """
        This namespace provides information about the local variables
        defined within a function's frame.

        Some ways to get this information can be::

            > print function.frame.lvars.size()

        """
        @utils.multicase()
        @classmethod
        def size(cls):
            '''Returns the size of the local variables for the current function.'''
            return cls.size(ui.current.function())
        @utils.multicase()
        @classmethod
        def size(cls, func):
            '''Returns the size of the local variables for the function `func`.'''
            fn = by(func)
            return fn.frsize
    vars = lvars    # XXX: ns alias

    class regs(object):
        """
        This namespace provides information about the registers that
        are saved when a function constructs its frame.

        An example of using this namespace::

            > print function.frame.regs.size(ea)

        """

        @utils.multicase()
        @classmethod
        def size(cls):
            '''Returns the number of bytes occupied by the saved registers in the current function.'''
            return cls.size(ui.current.function())
        @utils.multicase()
        @classmethod
        def size(cls, func):
            '''Returns the number of bytes occupied by the saved registers for the function `func`.'''
            fn = by(func)
            # include the size of a word for the pc because ida doesn't count it
            return fn.frregs + database.config.bits() / 8

get_frameid = utils.alias(frame.id, 'frame')
get_args_size = utils.alias(frame.args.size, 'frame.args')
get_vars_size = utils.alias(frame.lvars.size, 'frame.lvars')
get_regs_size = utils.alias(frame.regs.size, 'frame.regs')
get_spdelta = spdelta = utils.alias(frame.delta, 'frame')
arguments = args = frame.args

## instruction iteration/searching
## tagging
@utils.multicase()
def tag():
    '''Returns all the tags defined for the current function.'''
    return tag(ui.current.address())
@utils.multicase(key=basestring)
def tag(key):
    '''Returns the value of the tag identified by `key` for the current function.'''
    return tag(ui.current.address(), key)
@utils.multicase(key=basestring)
def tag(key, value):
    '''Sets the value for the tag `key` to `value` for the current function.'''
    return tag(ui.current.address(), key, value)
@utils.multicase(key=basestring)
def tag(func, key):
    '''Returns the value of the tag identified by `key` for the function `func`.'''
    res = tag(func)
    if key in res:
        return res[key]
    raise E.MissingFunctionTagError("{:s}.tag({!r}, {!r}) : Unable to read tag {!r} from function.".format(__name__, func, key, key))
@utils.multicase()
def tag(func):
    '''Returns all the tags defined for the function `func`.'''
    try:
        rt, ea = interface.addressOfRuntimeOrStatic(func)
    except E.FunctionNotFoundError:
        logging.warn("{:s}.tag({:s}) : Attempted to read tag from a non-function. Falling back to a database tag.".format(__name__, ("{:#x}" if isinstance(func, six.integer_types) else "{!r}").format(func)))
        return database.tag(func)

    if rt:
        logging.warn("{:s}.tag({:#x}) : Attempted to read tag from a runtime-linked address. Falling back to a database tag.".format(__name__, ea))
        return database.tag(ea)

    fn, repeatable = by_address(ea), True
    res = comment(fn, repeatable=False)
    d1 = internal.comment.decode(res)
    res = comment(fn, repeatable=True)
    d2 = internal.comment.decode(res)

    if d1.viewkeys() & d2.viewkeys():
        logging.info("{:s}.tag({:#x}) : Contents of both the repeatable and non-repeatable comment conflict with one another due to using the same key ({!r}). Giving the {:s} comment priority.".format(__name__, ea, ', '.join(d1.viewkeys() & d2.viewkeys()), 'repeatable' if repeatable else 'non-repeatable'))

    res = {}
    map(res.update, (d1, d2) if repeatable else (d2, d1))

    # add the function's name to the result
    fname = name(fn)
    if fname and database.type.flags(fn.startEA, idaapi.FF_NAME): res.setdefault('__name__', fname)

    # ..and now hand it off.
    return res
@utils.multicase(key=basestring)
def tag(func, key, value):
    '''Sets the value for the tag `key` to `value` for the function `func`.'''
    if value is None:
        raise E.InvalidParameterError("{:s}.tag({!r}) : Tried to set tag {!r} to an unsupported type.".format(__name__, ea, key))

    # Check to see if function tag is being applied to an import
    try:
        rt, ea = interface.addressOfRuntimeOrStatic(func)
    except E.FunctionNotFoundError:
        # If we're not even in a function, then use a database tag.
        logging.warn("{:s}.tag({:s}, {!r}, {!r}) : Attempted to set tag for a non-function. Falling back to a database tag.".format(__name__, ("{:#x}" if isinstance(func, six.integer_types) else "{!r}").format(func), key, value))
        return database.tag(func, key, value)

    # If so, then write the tag to the import
    if rt:
        logging.warn("{:s}.tag({:#x}, {!r}, {!r}) : Attempted to set tag for a runtime-linked symbol. Falling back to a database tag.".format(__name__, ea, key, value))
        return database.tag(ea, key, value)

    # Otherwise, it's a function.
    fn = by_address(ea)

    # if the user wants to change the '__name__' tag then update the function's name.
    if key == '__name__':
        return name(fn, value)

    # decode the comment, fetch the old key, re-assign the new key, and then re-encode it
    state = internal.comment.decode(comment(fn, repeatable=True))
    res, state[key] = state.get(key, None), value
    comment(fn, internal.comment.encode(state), repeatable=True)

    # if we weren't able to find a key in the dict, then one was added and we need to update its reference
    if res is None:
        internal.comment.globals.inc(fn.startEA, key)

    # return what we fetched from the dict
    return res
@utils.multicase(key=basestring, none=types.NoneType)
def tag(key, none):
    '''Removes the tag identified by `key` for the current function.'''
    return tag(ui.current.address(), key, None)
@utils.multicase(key=basestring, none=types.NoneType)
def tag(func, key, none):
    '''Removes the tag identified by `key` from the function `func`.'''

    # Check to see if function tag is being applied to an import
    try:
        rt, ea = interface.addressOfRuntimeOrStatic(func)
    except E.FunctionNotFoundError:
        # If we're not even in a function, then use a database tag.
        logging.warn("{:s}.tag({:s}, {!r}, {!s}) : Attempted to clear tag for a non-function. Falling back to a database tag.".format(__name__, ('{:#x}' if isinstance(func, six.integer_types) else '{!r}').format(func), key, none))
        return database.tag(func, key, none)

    # If so, then write the tag to the import
    if rt:
        logging.warn("{:s}.tag({:#x}, {!r}, {!s}) : Attempted to set tag for a runtime-linked symbol. Falling back to a database tag.".format(__name__, ea, key, none))
        return database.tag(ea, key, none)

    # Otherwise, it's a function.
    fn = by_address(ea)

    # if the user wants to remove the '__name__' tag then remove the name from the function.
    if key == '__name__':
        return name(fn, None)
    elif key == '__color__':
        return color(fn, None)

    # decode the comment, remove the key, and then re-encode it
    state = internal.comment.decode(comment(fn, repeatable=True))
    if key not in state:
        raise E.MissingFunctionTagError("{:s}.tag({:#x}, {!r}, {!s}) : Unable to remove tag {!r} from function.".format(__name__, fn.startEA, key, none, key))
    res = state.pop(key)
    comment(fn, internal.comment.encode(state), repeatable=True)

    # if we got here without raising an exception, then the tag was stored so update the cache
    internal.comment.globals.dec(fn.startEA, key)
    return res

@utils.multicase()
def tags():
    '''Returns all the content tags for the current function.'''
    return tags(ui.current.function())
@utils.multicase()
def tags(func):
    '''Returns all the content tags for the function `func`.'''
    ea = by(func).startEA
    return internal.comment.contents.name(ea)

# FIXME: consolidate this logic into the utils module
# FIXME: document this properly
@utils.multicase(tag=basestring)
def select(**boolean):
    '''Query the contents of the current function for any tags specified by `boolean`'''
    return select(ui.current.function(), **boolean)
@utils.multicase(tag=basestring)
def select(tag, *And, **boolean):
    '''Query the contents of the current function for the specified `tag` and any others specified as `And`.'''
    res = (tag,) + And
    boolean['And'] = tuple(set(boolean.get('And', set())).union(res))
    return select(ui.current.function(), **boolean)
@utils.multicase(tag=basestring)
def select(func, tag, *And, **boolean):
    '''Query the contents of the function `func` for the specified `tag` and any others specified as `And`.'''
    res = (tag,) + And
    boolean['And'] = tuple(set(boolean.get('And', set())).union(res))
    return select(func, **boolean)
@utils.multicase(tag=(builtins.set, builtins.list))
def select(func, tag, *And, **boolean):
    '''Query the contents of the function `func` for the specified `tag` and any others specified as `And`.'''
    res = set(builtins.list(tag) + builtins.list(And))
    boolean['And'] = tuple(set(boolean.get('And', set())).union(res))
    return select(func, **boolean)
@utils.multicase()
def select(func, **boolean):
    """Query the contents of the function `func` for any tags specified by `boolean`. Yields each address found along with the matching tags as a dictionary.

    If `And` contains an iterable then require the returned address contains them.
    If `Or` contains an iterable then include any other tags that are specified.
    """
    fn = by(func)
    containers = (builtins.tuple, builtins.set, builtins.list)
    boolean = {k : set(v if isinstance(v, containers) else {v}) for k, v in boolean.viewitems()}

    # nothing specific was queried, so just yield each tag
    if not boolean:
        for ea in internal.comment.contents.address(fn.startEA):
            ui.navigation.analyze(ea)
            res = database.tag(ea)
            if res: yield ea, res
        return

    # walk through every tagged address and cross-check it against query
    for ea in internal.comment.contents.address(fn.startEA):
        ui.navigation.analyze(ea)
        res, d = {}, database.tag(ea)

        # Or(|) includes any of the tags being queried
        Or = boolean.get('Or', set())
        res.update({key : value for key, value in six.iteritems(d) if key in Or})

        # And(&) includes any tags only if they include all the specified tagnames
        And = boolean.get('And', set())
        if And:
            if And.intersection(d.viewkeys()) == And:
                res.update({key : value for key, value in six.iteritems(d) if key in And})
            else: continue

        # if anything matched, then yield the address and the queried tags.
        if res: yield ea, res
    return

## referencing
@utils.multicase()
def down():
    '''Return all the functions that are called by the current function.'''
    return down(ui.current.function())
@utils.multicase()
def down(func):
    '''Return all the functions that are called by the function `func`.'''
    def codeRefs(fn):
        resultData, resultCode = [], []
        for ea in iterate(fn):
            if len(database.down(ea)) == 0:
                if database.type.is_code(ea) and instruction.is_call(ea):
                    logging.info("{:s}.down({:#x}) : Discovered a dynamically resolved call that is unable to be resolved. The instruction is {!r}.".format(__name__, fn.startEA, database.disassemble(ea)))
                    #resultCode.append((ea, 0))
                continue
            resultData.extend( (ea, x) for x in database.xref.data_down(ea) )
            resultCode.extend( (ea, x) for x in database.xref.code_down(ea) if fn.startEA == x or not contains(fn, x) )
        return resultData, resultCode
    fn = by(func)
    return sorted({d for _, d in codeRefs(fn)[1]})

@utils.multicase()
def up():
    '''Return all the functions that call the current function.'''
    return up(ui.current.address())
@utils.multicase()
def up(func):
    '''Return all the functions that call the function `func`.'''
    rt, ea = interface.addressOfRuntimeOrStatic(func)
    # runtime
    if rt:
        return database.up(ea)
    # regular
    return database.up(ea)

@utils.multicase()
def switches():
    '''Yield each switch found in the current function.'''
    return switches(ui.current.function())
@utils.multicase()
def switches(func):
    '''Yield each switch found in the function identifed by `func`.'''
    for ea in iterate(func):
        res = idaapi.get_switch_info_ex(ea)
        if res: yield interface.switch_t(res)
    return

class type(object):
    """
    This namespace allows one to query type information about a
    specified function. This allows one to get any attributes that IDA
    or a user has applied to a function within the database. This alows
    one to filter functions according to their particular attributes.

    Some simple ways of getting information about a function::

        > print function.type.has_noframe()
        > for ea in filter(function.type.is_library, database.functions()): ...

    """
    @utils.multicase()
    @classmethod
    def has_noframe(cls):
        '''Return true if the current function has no frame.'''
        return cls.has_noframe(ui.current.function())
    @utils.multicase()
    @classmethod
    def has_noframe(cls, func):
        '''Return true if the function `func` has no frame.'''
        fn = by(func)
        return not cls.is_thunk(fn) and (fn.flags & idaapi.FUNC_FRAME == 0)
    noframeQ = utils.alias(has_noframe, 'type')

    @utils.multicase()
    @classmethod
    def has_name(cls):
        '''Return true if the current function has a user-defined name.'''
        return cls.has_name(ui.current.function())
    @utils.multicase()
    @classmethod
    def has_name(cls, func):
        '''Return true if the function `func` has a user-defined name.'''
        ea = address(func)
        return database.type.has_customname(ea)
    nameQ = customnameQ = has_customname = utils.alias(has_name, 'type')

    @utils.multicase()
    @classmethod
    def has_noreturn(cls):
        '''Return true if the current function does not return.'''
        return cls.has_noreturn(ui.current.function())
    @utils.multicase()
    @classmethod
    def has_noreturn(cls, func):
        '''Return true if the function `func` does not return.'''
        fn = by(func)
        return not cls.is_thunk(fn) and (fn.flags & idaapi.FUNC_NORET == idaapi.FUNC_NORET)
    noreturnQ = utils.alias(has_noreturn, 'type')

    @utils.multicase()
    @classmethod
    def is_library(cls):
        '''Return true if the current function is considered a library function.'''
        return cls.is_library(ui.current.function())
    @utils.multicase()
    @classmethod
    def is_library(cls, func):
        '''Return true if the function `func` is considered a library function.'''
        fn = by(func)
        return fn.flags & idaapi.FUNC_LIB == idaapi.FUNC_LIB
    libraryQ = utils.alias(is_library, 'type')

    @utils.multicase()
    @classmethod
    def is_thunk(cls):
        '''Return true if the current function is considered a code thunk.'''
        return cls.is_thunk(ui.current.function())
    @utils.multicase()
    @classmethod
    def is_thunk(cls, func):
        '''Return true if the function `func` is considered a code thunk.'''
        fn = by(func)
        return fn.flags & idaapi.FUNC_THUNK == idaapi.FUNC_THUNK
    thunkQ = utils.alias(is_thunk, 'type')

# FIXME: document this
#def refs(func, member):
#    xl, fn = idaapi.xreflist_t(), by(func)
#    idaapi.build_stkvar_xrefs(xl, fn, member.ptr)
#    x.ea, x.opnum, x.type
#    ref_types = {
#        0  : 'Data_Unknown',
#        1  : 'Data_Offset',
#        2  : 'Data_Write',
#        3  : 'Data_Read',
#        4  : 'Data_Text',
#        5  : 'Data_Informational',
#        16 : 'Code_Far_Call',
#        17 : 'Code_Near_Call',
#        18 : 'Code_Far_Jump',
#        19 : 'Code_Near_Jump',
#        20 : 'Code_User',
#        21 : 'Ordinary_Flow'
#    }
#    return [(x.ea, x.opnum) for x in xl]
