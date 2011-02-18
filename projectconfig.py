#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4; indent-tabs-mode: nil; coding: utf-8; -*-
# vim:set ft=python ts=4 sw=4 sts=4 autoindent:


'''
Per-project configuration functionality for
Brat Rapid Annotation Tool (brat)
'''

import re

from message import display_message

# TODO: this whole thing is an ugly hack. Event types should be read
# from a proper ontology.

class InvalidProjectConfigException(Exception):
    pass

__event_type_hierarchy_filename  = 'event_types.conf'
__entity_type_hierarchy_filename = 'entity_types.conf'

__default_event_type_hierarchy  = """
!event
 GO:0005515 | protein binding	Theme+:Protein
 GO:0010467 | gene expression	Theme:Protein"""

__default_entity_type_hierarchy = """
Protein
Entity"""

# caches to avoid re-reading on every invocation of getters
__directory_entity_type_hierarchy = {}
__directory_event_type_hierarchy = {}
__directory_entity_types = {}
__directory_event_types = {}
__directory_node_by_storage_term = {}

def term_interface_form(t):
    """
    Returns a form of the term suitable for display to user.
    """

    # abbreviated form of the ontology term for display
    # to annotators, e.g. "protein phosphorylation"
    # -> "Phosphorylation"
    if re.match(r'^protein [a-z]*ation', t):
        # cut away initial "protein"
        t = re.sub(r'^protein ', '', t)
        t = t[0].upper()+t[1:]
        return t
    else:
        return t[0].upper()+t[1:]

def term_storage_form(t):
    """
    Returns a form of the the given term suitable for storage in standoff format.
    """
    return term_interface_form(t).replace(" ","_")


class TypeHierarchyNode:
    """
    Represents a node in a simple hierarchical ontology.
    """
    def __init__(self, terms, args):
        self.terms, self.args = terms, args

        if len(terms) == 0 or len([t for t in terms if t == ""]) != 0:
            display_message("Empty term in type configuration" % (a, args), "debug", -1)
            raise InvalidProjectConfigException

        # by convention, the last of the listed terms is used
        # as the primary term
        self.primary_term = self.terms[-1]

        # unused if any of the terms marked with "!"
        self.unused = False
        for i in range(len(self.terms)):
            if self.terms[i][0] == "!":
                self.terms[i]= self.terms[i][1:]
                self.unused = True
        self.children = []

        # TODO: cleaner and more localized parsing
        self.arguments = []
        self.mandatory_arguments = []
        self.roles_by_type = {}
        for a in self.args:
            a = a.strip()
            m = re.match(r'^(.*?):(.*)$', a)
            if not m:
                display_message("Failed to parse argument %s (args: %s)" % (a, args), "debug", -1)
                raise InvalidProjectConfigException
            role, atypes = m.groups()

            if role[-1:] not in ("?", "*"):
                mandatory_role = True
            else:
                mandatory_role = False

            if role[-1:] in ("?", "*", "+"):
                role = role[:-1]

            if mandatory_role:
                self.mandatory_arguments.append(role)

            for atype in atypes.split("|"):
                if atype.strip() == "":
                    raise InvalidProjectConfigException
                atype = term_storage_form(atype)

                self.arguments.append((role, atype))

                if atype not in self.roles_by_type:
                    self.roles_by_type[atype] = []
                self.roles_by_type[atype].append(role)

    def __norm(self, t):
        return t.lower().replace(" ", "_")

    def storage_term(self):
        return term_storage_form(self.primary_term)

    def interface_term(self):
        return term_interface_form(self.primary_term)


def __read_term_hierarchy(input):
    root_nodes    = []
    last_node_at_depth = {}

    for l in input:
        # skip empties and lines starting with '#'
        if l.strip() == '' or re.match(r'^\s*#', l):
            continue

        # interpret lines of only hyphens as separators
        # for display
        if re.match(r'^\s*-+\s*$', l):
            # TODO: proper placeholder and placing
            root_nodes.append("SEPARATOR")
            continue

        m = re.match(r'^(\s*)([^\t]+)(?:\t(.*))?$', l)
        assert m, "Error parsing line: '%s'" % l
        indent, terms, args = m.groups()
        terms = [t.strip() for t in terms.split("|") if t.strip() != ""]
        if args is None or args.strip() == "":
            args = []
        else:
            args = [a.strip() for a in args.split(",") if a.strip() != ""]

        # depth in the ontology corresponds to the number of
        # spaces in the initial indent.
        depth = len(indent)

        n = TypeHierarchyNode(terms, args)
        if depth == 0:
            # root level, no children assignments
            root_nodes.append(n)
        else:
            # assign as child of last node at the depth of the parent
            assert depth-1 in last_node_at_depth, "Error: no parent for '%s'" % l
            last_node_at_depth[depth-1].children.append(n)
        last_node_at_depth[depth] = n

    return root_nodes


def __read_term_hierarchy_file(filename, default):
    try:
        f = open(filename, 'r')
        term_hierarchy = f.read()
        f.close()
    except:
        # TODO: specific exception handling
        term_hierarchy = default
    return term_hierarchy


def __parse_term_hierarchy(hierarchy, default, source):
    try:
        root_nodes = __read_term_hierarchy(hierarchy.split("\n"))
    except:
        # TODO: specific exception handling
        display_message("Project configuration: error parsing types from %s. Configuration may be wrong." % source, "warning", 5)
        root_nodes = default
    return root_nodes

def __get_type_hierarchy(directory, filename, default_hierarchy, min_hierarchy):
    type_hierarchy = None

    if directory is not None:
        # try to find a config file in the directory
        import os
        fn = os.path.join(directory, filename)
        source = fn
        type_hierarchy = __read_term_hierarchy_file(fn, None)

    if type_hierarchy is None:
        # if we didn't get a directory-specific one, try default dir
        # and fall back to the default hierarchy
        #
        source = filename
        # too noisy
        # display_message("Project configuration: type config %s not found in %s" % (filename, directory))
        type_hierarchy = __read_term_hierarchy_file(filename, default_hierarchy)
        if type_hierarchy == default_hierarchy:
            source = "[default hierarchy]"
        
    # try to parse what we got, fall back to minimal hierarchy
    root_nodes = __parse_term_hierarchy(type_hierarchy, min_hierarchy, source)

    return root_nodes

def get_entity_type_hierarchy(directory):
    global __directory_entity_type_hierarchy

    if directory not in __directory_entity_type_hierarchy:
        h = __get_type_hierarchy(directory,
                                 __entity_type_hierarchy_filename,
                                 __default_entity_type_hierarchy,
                                 [TypeHierarchyNode(["protein"], [])])
        __directory_entity_type_hierarchy[directory] = h

    return __directory_entity_type_hierarchy[directory]
    
     
def get_event_type_hierarchy(directory):
    global __directory_event_type_hierarchy

    if directory not in __directory_event_type_hierarchy:
        h =  __get_type_hierarchy(directory,
                                  __event_type_hierarchy_filename,
                                  __default_event_type_hierarchy,
                                  [TypeHierarchyNode(["event"], ["Theme:Protein"])])
        __directory_event_type_hierarchy[directory] = h

    return __directory_event_type_hierarchy[directory]

def __collect_type_list(node, collected):
    if node == "SEPARATOR":
        return collected

    collected.append(node)

    for c in node.children:
        __collect_type_list(c, collected)

    return collected

def pc_get_type_list(directory, hierarchy):
    root_nodes = hierarchy
    types = []
    for n in root_nodes:
        __collect_type_list(n, types)
    return types

def pc_get_entity_type_list(directory):
    global __directory_entity_types

    if directory not in __directory_entity_types:
        __directory_entity_types[directory] = pc_get_type_list(directory, get_entity_type_hierarchy(directory))

    return __directory_entity_types[directory]

def pc_get_event_type_list(directory):
    global __directory_event_types

    if directory not in __directory_event_types:
        __directory_event_types[directory] = pc_get_type_list(directory, get_event_type_hierarchy(directory))

    return __directory_event_types[directory]

def pc_get_node_by_term(directory, term):
    global __directory_node_by_storage_term

    if directory not in __directory_node_by_storage_term:
        __directory_node_by_storage_term[directory] = {}
        d = {}
        for e in pc_get_entity_type_list(directory) + pc_get_event_type_list(directory):
            t = e.storage_term()
            if t in d:
                display_message("Project configuration: interface term %s matches multiple types (incl. '%s' and '%s'). Configuration may be wrong." % (t, d[t].storage_term(), e.storage_term()), "warning", 5)
            d[t] = e
        __directory_node_by_storage_term[directory] = d

    return __directory_node_by_storage_term[directory].get(term, None)

# fallback for missing or partial config: these are highly likely to
# be entity (as opposed to an event or relation) types.
# TODO: remove this workaround once the configs stabilize.
very_likely_physical_entity_types = [
    'Protein',
    'Entity',
    'Organism',
    'Chemical',
    'Two-component-system',
    'Regulon-operon',
    # for more PTM annotation
    'Protein_family_or_group',
    'DNA_domain_or_region',
    'Protein_domain_or_region',
    'Amino_acid_monomer',
    'Carbohydrate',
    # for AZ corpus
    'Cell_type',
    'Drug_or_compound',
    'Gene_or_gene_product',
    'Pathway',
    'Tissue',
    #'Not_sure',
    #'Other',
    'Other_pharmaceutical_agent',
    ]

class ProjectConfiguration(object):
    def __init__(self, directory):
        # debugging
        if directory[:1] != "/":
            display_message("Warning: project config received relative directory, configuration may not be found.", "debug", -1)
        self.directory = directory
        self.__entity_type_dict = None
        self.__event_type_dict = None

    def arc_types_from(self, from_ann):
        return self.arc_types_from_to(from_ann)

    def arc_types_from_to(self, from_ann, to_ann="<ANY>"):
        """
        Returns the possible arc types that can connect an annotation
        of type from_ann to an annotation of type to_ann.
        If to_ann has the value \"<ANY>\", returns all possible arc types.
        """

        def unique_preserve_order(iterable):
            seen = set()
            uniqued = []
            for i in iterable:
                if i not in seen:
                    seen.add(i)
                    uniqued.append(i)
            return uniqued

        from_node = pc_get_node_by_term(self.directory, from_ann)
        if from_node is None:
            display_message("Project configuration: unknown type %s. Configuration may be wrong." % from_ann, "warning")
            return []
        if to_ann == "<ANY>":
            return unique_preserve_order([role for role, type in from_node.arguments])

        # specific hits
        if to_ann not in from_node.roles_by_type:
            types = []
        else:
            types = from_node.roles_by_type[to_ann]

        # generic arguments
        if self.is_event_type(to_ann) and '<EVENT>' in from_node.roles_by_type:
            types += from_node.roles_by_type['<EVENT>']
        if self.is_physical_entity_type(to_ann) and '<ENTITY>' in from_node.roles_by_type:
            types += from_node.roles_by_type['<ENTITY>']

        return unique_preserve_order(types)

    def get_event_types(self):
        return [t.storage_term() for t in pc_get_event_type_list(self.directory)]

    def get_entity_types(self):
        return [t.storage_term() for t in pc_get_entity_type_list(self.directory)]

    def is_physical_entity_type(self, t):
        # TODO: remove this temporary hack
        if t in very_likely_physical_entity_types:
            return True

        return t in self.get_entity_types()

    def is_event_type(self, t):
        return t in self.get_event_types()

    def type_category(self, t):
        """
        Returns the category of the given type t.
        The categories can be compared for equivalence but offer
        no other interface.
        """
        if self.is_physical_entity_type(t):
            return "PHYSICAL"
        elif self.is_event_type(t):
            return "EVENT"
        else:
            # TODO:
            return "OTHER"
