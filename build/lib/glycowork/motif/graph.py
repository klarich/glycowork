import re
import copy
import networkx as nx
from glycowork.glycan_data.loader import lib, unwrap, find_nth, df_glycan
from glycowork.motif.processing import min_process_glycans
import numpy as np
import pandas as pd
from scipy.sparse.linalg import eigsh
  

def character_to_label(character, libr = None):
  """tokenizes character by indexing passed library\n
  | Arguments:
  | :-
  | character (string): character to index
  | libr (list): list of library items\n
  | Returns:
  | :-
  | Returns index of character in library
  """
  if libr is None:
    libr = lib
  character_label = libr.index(character)
  return character_label

def string_to_labels(character_string, libr = None):
  """tokenizes word by indexing characters in passed library\n
  | Arguments:
  | :-
  | character_string (string): string of characters to index
  | libr (list): list of library items\n
  | Returns:
  | :-
  | Returns indexes of characters in library
  """
  if libr is None:
    libr = lib
  return list(map(lambda character: character_to_label(character, libr), character_string))

def evaluate_adjacency(glycan_part, adjustment):
  """checks whether two glycoletters are adjacent in the graph-to-be-constructed\n
  | Arguments:
  | :-
  | glycan_part (string): residual part of a glycan from within glycan_to_graph
  | adjustment (int): number of characters to allow for extra length (consequence of tokenizing glycoletters)\n
  | Returns:
  | :-
  | Returns True if adjacent and False if not
  """
  #check whether glycoletters are adjacent in the main chain
  if any([glycan_part[-1] == '(', glycan_part[-1] == ')']) and len(glycan_part) < 2+adjustment:
    return True
  #check whether glycoletters are connected but separated by a branch delimiter
  elif glycan_part[-1] == ']':
    if any([glycan_part[:-1][-1] == '(', glycan_part[:-1][-1] == ')']) and len(glycan_part[:-1]) < 2+adjustment:
      return True
    else:
      return False
  return False

def bracket_removal(glycan_part):
  """iteratively removes (nested) branches between start and end of glycan_part\n
  | Arguments:
  | :-
  | glycan_part (string): residual part of a glycan from within glycan_to_graph\n
  | Returns:
  | :-
  | Returns glycan_part without interfering branches
  """
  while bool(re.search('\[[^\[\]]+\]', glycan_part)):
    glycan_part = re.sub('\[[^\[\]]+\]', '', glycan_part)
  return glycan_part

def glycan_to_graph(glycan):
  """the monumental function for converting glycans into graphs\n
  | Arguments:
  | :-
  | glycan (string): IUPAC-condensed glycan sequence\n
  | Returns:
  | :-
  | (1) a dictionary of node : monosaccharide/linkage
  | (2) an adjacency matrix of size glycoletter X glycoletter
  """
  #get glycoletters
  glycan_proc = min_process_glycans([glycan])[0]
  #map glycoletters to integers
  mask_dic = {k:glycan_proc[k] for k in range(len(glycan_proc))}
  for k,j in mask_dic.items():
    glycan = glycan.replace(j, str(k), 1)
  #initialize adjacency matrix
  adj_matrix = np.zeros((len(glycan_proc), len(glycan_proc)), dtype = int)
  #loop through each pair of glycoletters
  for k in range(len(mask_dic)):
    for j in range(len(mask_dic)):
      if k < j:
        #integers that are in place of glycoletters go up from 1 character (0-9) to 3 characters (>99)
        if k >= 100:
          adjustment = 2
        elif k >= 10:
          adjustment = 1
        else:
          adjustment = 0
        #subset the part of the glycan that is bookended by k and j
        glycan_part = glycan[glycan.index(str(k))+1:glycan.index(str(j))]
        #immediately adjacent residues
        if evaluate_adjacency(glycan_part, adjustment):
          adj_matrix[k,j] = 1
          continue
        #adjacent residues separated by branches in the string
        if len(bracket_removal(glycan_part)) <= 2+adjustment:
          glycan_part = bracket_removal(glycan_part)
          if evaluate_adjacency(glycan_part, adjustment):
                adj_matrix[k,j] = 1
                continue  
  return mask_dic, adj_matrix

def glycan_to_nxGraph_int(glycan, libr = None,
                      termini = 'ignore', termini_list = None,
                      override_reducing_end = False):
  """converts glycans into networkx graphs\n
  | Arguments:
  | :-
  | glycan (string): glycan in IUPAC-condensed format
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used
  | termini (string): whether to encode terminal/internal position of monosaccharides, 'ignore' for skipping, 'calc' for automatic annotation, or 'provided' if this information is provided in termini_list; default:'ignore'
  | termini_list (list): list of monosaccharide/linkage positions (from 'terminal','internal', and 'flexible')
  | override_reducing_end (bool): if True, it allows graph generation for glycans ending in a linkage; though the output doesn't work with all downstream functions; default:False\n
  | Returns:
  | :-
  | Returns networkx graph object of glycan
  """
  if libr is None:
    libr = lib
  #this allows to make glycan graphs of motifs ending in a linkage
  if override_reducing_end and glycan[-1] == ')':
    glycan = glycan + 'Hex'
  #map glycan string to node labels and adjacency matrix
  node_dict, adj_matrix = glycan_to_graph(glycan)
  #convert adjacency matrix to networkx graph
  if len(node_dict) > 1:
    g1 = nx.from_numpy_matrix(adj_matrix)
    #needed for compatibility with monosaccharide-only graphs (size = 1)
    for n1, n2, d in g1.edges(data = True):
      del d['weight']
  else:
    g1 = nx.Graph()  
    g1.add_node(0)
  #remove the helper monosaccharide if used
  if override_reducing_end:
    if glycan[-1] == 'x':
      g1.remove_node(len(g1.nodes) - 1)
  #add node labels
  nx.set_node_attributes(g1, {k:libr.index(node_dict[k]) for k in range(len(node_dict))}, 'labels')
  nx.set_node_attributes(g1, {k:node_dict[k] for k in range(len(node_dict))}, 'string_labels')
  if termini == 'ignore':
    pass
  elif termini == 'calc':
    nx.set_node_attributes(g1, {k:'terminal' if g1.degree[k] == 1 else 'internal' for k in g1.nodes()}, 'termini')
  elif termini == 'provided':
    nx.set_node_attributes(g1, {k:j for k,j in zip(g1.nodes(), termini_list)}, 'termini')
  return g1

def glycan_to_nxGraph(glycan, libr = None,
                      termini = 'ignore', termini_list = None,
                      override_reducing_end = False):
  """wrapper for converting glycans into networkx graphs; also works with floating substituents\n
  | Arguments:
  | :-
  | glycan (string): glycan in IUPAC-condensed format
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used
  | termini (string): whether to encode terminal/internal position of monosaccharides, 'ignore' for skipping, 'calc' for automatic annotation, or 'provided' if this information is provided in termini_list; default:'ignore'
  | termini_list (list): list of monosaccharide/linkage positions (from 'terminal','internal', and 'flexible')
  | override_reducing_end (bool): if True, it allows graph generation for glycans ending in a linkage; though the output doesn't work with all downstream functions; default:False\n
  | Returns:
  | :-
  | Returns networkx graph object of glycan
  """
  if libr is None:
    libr = lib
  if '{' in glycan:
    parts = glycan.replace('}','{').split('{')
    parts = [k for k in parts if len(k) > 0]
    parts = [glycan_to_nxGraph_int(k, libr = libr, termini = termini,
                                   termini_list = termini_list, override_reducing_end = True) for k in parts]
    len_org = len(parts[-1].nodes())
    for p in range(len(parts)-1):
      parts[p] = nx.relabel_nodes(parts[p], {pn:pn+len_org for pn in parts[p].nodes()})
      len_org += len(parts[p].nodes())
    g1 = nx.algorithms.operators.all.compose_all(parts)
  else:
    g1 = glycan_to_nxGraph_int(glycan, libr = libr, termini = termini,
                                   termini_list = termini_list, override_reducing_end = override_reducing_end)
  return g1

def ensure_graph(glycan, libr = None):
  """ensures function compatibility with string glycans and graph glycans\n
  | Arguments:
  | :-
  | glycan (string or networkx graph): glycan in IUPAC-condensed format or as a networkx graph
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-
  | Returns networkx graph object of glycan
  """
  if libr is None:
    libr = lib
  if isinstance(glycan, str):
    return glycan_to_nxGraph(glycan, libr = libr)
  else:
    return glycan

def categorical_node_match_wildcard(attr, default, wildcard_list):
  if isinstance(attr, str):
    def match(data1, data2):
      if data1['string_labels'] in wildcard_list:
        return True
      elif data2['string_labels'] in wildcard_list:
        return True
      else:
        return data1.get(attr, default) == data2.get(attr, default)
  else:
    attrs = list(zip(attr, default))
    def match(data1, data2):
      return all(data1.get(attr, d) == data2.get(attr, d) for attr, d in attrs)
  return match

def categorical_termini_match(attr1, attr2, default1, default2):
  if isinstance(attr1, str):
    def match(data1, data2):
      if data1[attr2] in ['flexible']:
        return all([data1.get(attr1, default1) == data2.get(attr1, default1), True])
      elif data2[attr2] in ['flexible']:
        return all([data1.get(attr1, default1) == data2.get(attr1, default1), True])
      else:
        return all([data1.get(attr1, default1) == data2.get(attr1, default1), data1.get(attr2, default2) == data2.get(attr2, default2)])
  else:
    attrs = list(zip(attr, default))
    def match(data1, data2):
      return all(data1.get(attr, d) == data2.get(attr, d) for attr, d in attrs)
  return match

def compare_glycans(glycan_a, glycan_b, libr = None,
                    wildcards = False, wildcard_list = []):
  """returns True if glycans are the same and False if not\n
  | Arguments:
  | :-
  | glycan_a (string or networkx object): glycan in IUPAC-condensed format or as a precomputed networkx object
  | glycan_b (stringor networkx object): glycan in IUPAC-condensed format or as a precomputed networkx object
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used
  | wildcards (bool): set to True to allow wildcards (e.g., '?1-?', 'monosaccharide'); default is False
  | wildcard_list (list): list of wildcards to consider, in the form of '?1-?' etc.\n
  | Returns:
  | :-  
  | Returns True if two glycans are the same and False if not
  """
  if libr is None:
    libr = lib
  if isinstance(glycan_a, str):
    #check whether glycan_a and glycan_b have the same length
    if len(set([len(k) for k in min_process_glycans([glycan_a, glycan_b])])) == 1:
      g1 = glycan_to_nxGraph(glycan_a, libr = libr)
      g2 = glycan_to_nxGraph(glycan_b, libr = libr)
    else:
      return False
  else:
    g1 = glycan_a
    g2 = glycan_b
  if len(g1.nodes) == len(g2.nodes):
    if wildcards:
      return nx.is_isomorphic(g1, g2, node_match = categorical_node_match_wildcard('labels', len(libr), wildcard_list))
    else:
      #first check whether components of both glycan graphs are identical, then check graph isomorphism (costly)
      if sorted(''.join(nx.get_node_attributes(g1, "string_labels").values())) == sorted(''.join(nx.get_node_attributes(g2, "string_labels").values())):
        return nx.is_isomorphic(g1, g2, node_match = nx.algorithms.isomorphism.categorical_node_match('labels', len(libr)))
      else:
        return False
  else:
    return False


def subgraph_isomorphism(glycan, motif, libr = None,
                         extra = 'ignore', wildcard_list = [],
                         termini_list = [], count = False):
  """returns True if motif is in glycan and False if not\n
  | Arguments:
  | :-
  | glycan (string): glycan in IUPAC-condensed format or as graph in NetworkX format
  | motif (string): glycan motif in IUPAC-condensed format
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used
  | extra (string): 'ignore' skips this, 'wildcards' allows for wildcard matching', and 'termini' allows for positional matching; default:'ignore'
  | wildcard_list (list): list of wildcard names (such as '?1-?', 'Hex', 'HexNAc', 'Sia')
  | termini_list (list): list of monosaccharide/linkage positions (from 'terminal','internal', and 'flexible')
  | count (bool): whether to return the number or absence/presence of motifs; default:False\n
  | Returns:
  | :-
  | Returns True if motif is in glycan and False if not
  """
  if libr is None:
    libr = lib
  if len(wildcard_list) >= 1:
    wildcard_list = [libr.index(k) for k in wildcard_list]
  motif_comp = min_process_glycans([motif])[0]
  if isinstance(glycan, str):
    if extra == 'termini':
      g1 = glycan_to_nxGraph(glycan, libr = libr, termini = 'calc')
      g2 = glycan_to_nxGraph(motif, libr = libr, termini = 'provided',
                             termini_list = termini_list, override_reducing_end = True)
    else:
      g1 = glycan_to_nxGraph(glycan, libr = libr)
      g2 = glycan_to_nxGraph(motif, libr = libr, override_reducing_end = True)
  else:
    g1 = copy.deepcopy(glycan)
    if extra == 'termini':
      g2 = glycan_to_nxGraph(motif, libr = libr, termini = 'provided',
                             termini_list = termini_list, override_reducing_end = True)
    else:
      g2 = glycan_to_nxGraph(motif, libr = libr, override_reducing_end = True)

  #check whether length of glycan is larger or equal than the motif
  if len(g1.nodes) >= len(g2.nodes): 
    if extra == 'ignore':
      if all(k in nx.get_node_attributes(g1, "string_labels").values() for k in motif_comp):
        graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = nx.algorithms.isomorphism.categorical_node_match('labels', len(libr)))
      else:
        if count:
          return 0
        else:
          return False
    elif extra == 'wildcards':
      graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = categorical_node_match_wildcard('labels', len(libr), wildcard_list))
    elif extra == 'termini':
      if all(k in nx.get_node_attributes(g1, "string_labels").values() for k in motif_comp):
        graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = categorical_termini_match('labels', 'termini', len(libr), 'flexible'))
      else:
        if count:
          return 0
        else:
          return False
        
    #count motif occurrence
    if count:
      counts = 0
      while graph_pair.subgraph_is_isomorphic():
        counts += 1
        g1.remove_nodes_from(graph_pair.mapping.keys())
        if extra == 'ignore':
          if all(k in nx.get_node_attributes(g1, "string_labels").values() for k in motif_comp):
            graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = nx.algorithms.isomorphism.categorical_node_match('labels', len(libr)))
          else:
            return counts
        elif extra == 'wildcards':
          graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = categorical_node_match_wildcard('labels', len(libr), wildcard_list))
        elif extra == 'termini':
          if all(k in nx.get_node_attributes(g1, "string_labels").values() for k in motif_comp):
            graph_pair = nx.algorithms.isomorphism.GraphMatcher(g1,g2,node_match = categorical_termini_match('labels', 'termini', len(libr), 'flexible'))
          else:
            return counts
      return counts
    else: return graph_pair.subgraph_is_isomorphic()
  else:
    if count:
      return 0
    else:
      return False

def generate_graph_features(glycan, glycan_graph = True, libr = None, label = 'network'):
    """compute graph features of glycan\n
    | Arguments:
    | :-
    | glycan (string or networkx object): glycan in IUPAC-condensed format (or glycan network if glycan_graph=False)
    | glycan_graph (bool): True expects a glycan, False expects a network (from construct_network); default:True
    | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used
    | label (string): Label to place in output dataframe if glycan_graph=False; default:'network'\n
    | Returns:
    | :-
    | Returns a pandas dataframe with different graph features as columns and glycan as row
    """
    if libr is None:
      libr = lib
    if glycan_graph:
      g = ensure_graph(glycan, libr = libr)
      #nbr of different node features:
      nbr_node_types = len(set(nx.get_node_attributes(g, "labels")))
    else:
      g = glycan
      glycan = label
      nbr_node_types = len(set(list(g.nodes())))
    #adjacency matrix:
    A = nx.to_numpy_matrix(g)
    N = A.shape[0]
    if nx.is_directed(g):
      directed = True
    else:
      directed = False
    if not directed:
      if nx.is_connected(g):
        diameter = nx.algorithms.distance_measures.diameter(g)
      else:
        diameter = np.nan
    else:
      diameter = np.nan
    deg = np.array([np.sum(A[i,:]) for i in range(N)])
    dens = np.sum(deg)/2
    avgDeg = np.mean(deg)
    varDeg = np.var(deg)
    maxDeg = np.max(deg)
    nbrDeg4 = np.sum(deg > 3)
    branching = np.sum(deg > 2)
    nbrLeaves = np.sum(deg == 1)
    deg_to_leaves = np.array([np.sum(A[:,deg == 1]) for i in range(N)])
    max_deg_leaves = np.max(deg_to_leaves)
    mean_deg_leaves = np.mean(deg_to_leaves)
    deg_assort = nx.degree_assortativity_coefficient(g)
    betweeness_centr = np.array(pd.DataFrame(nx.betweenness_centrality(g), index = [0]).iloc[0,:])
    betweeness = np.mean(betweeness_centr)
    betwVar = np.var(betweeness_centr)
    betwMax = np.max(betweeness_centr)
    betwMin = np.min(betweeness_centr)
    eigen = np.array(pd.DataFrame(nx.katz_centrality_numpy(g), index = [0]).iloc[0,:])
    eigenMax = np.max(eigen)
    eigenMin = np.min(eigen)
    eigenAvg = np.mean(eigen)
    eigenVar = np.var(eigen)
    close = np.array(pd.DataFrame(nx.closeness_centrality(g), index = [0]).iloc[0,:])
    closeMax = np.max(close)
    closeMin = np.min(close)
    closeAvg = np.mean(close)
    closeVar = np.var(close)
    if not directed:
      if nx.is_connected(g):
        flow = np.array(pd.DataFrame(nx.current_flow_betweenness_centrality(g), index = [0]).iloc[0,:])
        flowMax = np.max(flow)
        flowMin = np.min(flow)
        flowAvg = np.mean(flow)
        flowVar = np.var(flow)
        flow_edge = np.array(pd.DataFrame(nx.edge_current_flow_betweenness_centrality(g), index = [0]).iloc[0,:])
        flow_edgeMax = np.max(flow_edge)
        flow_edgeMin = np.min(flow_edge)
        flow_edgeAvg = np.mean(flow_edge)
        flow_edgeVar = np.var(flow_edge)
      else:
        flow = np.nan
        flowMax = np.nan
        flowMin = np.nan
        flowAvg = np.nan
        flowVar = np.nan
        flow_edge = np.nan
        flow_edgeMax = np.nan
        flow_edgeMin = np.nan
        flow_edgeAvg = np.nan
        flow_edgeVar = np.nan
    else:
      flow = np.nan
      flowMax = np.nan
      flowMin = np.nan
      flowAvg = np.nan
      flowVar = np.nan
      flow_edge = np.nan
      flow_edgeMax = np.nan
      flow_edgeMin = np.nan
      flow_edgeAvg = np.nan
      flow_edgeVar = np.nan
    load = np.array(pd.DataFrame(nx.load_centrality(g), index = [0]).iloc[0,:])
    loadMax = np.max(load)
    loadMin = np.min(load)
    loadAvg = np.mean(load)
    loadVar = np.var(load)
    harm = np.array(pd.DataFrame(nx.harmonic_centrality(g), index = [0]).iloc[0,:])
    harmMax = np.max(harm)
    harmMin = np.min(harm)
    harmAvg = np.mean(harm)
    harmVar = np.var(harm)
    if not directed:
      if nx.is_connected(g):
        secorder = np.array(pd.DataFrame(nx.second_order_centrality(g), index = [0]).iloc[0,:])
        secorderMax = np.max(secorder)
        secorderMin = np.min(secorder)
        secorderAvg = np.mean(secorder)
        secorderVar = np.var(secorder)
      else:
        secorder = np.nan
        secorderMax = np.nan
        secorderMin = np.nan
        secorderAvg = np.nan
        secorderVar = np.nan
    else:
      secorder = np.nan
      secorderMax = np.nan
      secorderMin = np.nan
      secorderAvg = np.nan
      secorderVar = np.nan
    x = np.array([len(nx.k_corona(g,k).nodes()) for k in range(N)])
    size_corona = x[x > 0][-1]
    k_corona = np.where(x == x[x > 0][-1])[0][-1]
    x = np.array([len(nx.k_core(g,k).nodes()) for k in range(N)])
    size_core = x[x > 0][-1]
    k_core = np.where(x == x[x > 0][-1])[0][-1]
    M = ((A + np.diag(np.ones(N))).T/(deg + 1)).T
    eigval, vec = eigsh(M, 2, which = 'LM')
    egap = 1 - eigval[0]
    distr = np.abs(vec[:,-1])
    distr = distr/sum(distr)
    entropyStation = np.sum(distr*np.log(distr))
    features = np.array(
        [diameter, branching, nbrLeaves, avgDeg, varDeg, maxDeg, nbrDeg4, max_deg_leaves, mean_deg_leaves,
         deg_assort, betweeness, betwVar, betwMax, eigenMax, eigenMin, eigenAvg, eigenVar, closeMax, closeMin,
         closeAvg, closeVar, flowMax, flowAvg, flowVar,
         flow_edgeMax, flow_edgeMin, flow_edgeAvg, flow_edgeVar,
         loadMax, loadAvg, loadVar,
         harmMax, harmMin, harmAvg, harmVar,
         secorderMax, secorderMin, secorderAvg, secorderVar,
         size_corona, size_core, nbr_node_types,
         egap, entropyStation, N, dens
         ])
    col_names = ['diameter', 'branching', 'nbrLeaves', 'avgDeg', 'varDeg',
                 'maxDeg', 'nbrDeg4', 'max_deg_leaves', 'mean_deg_leaves',
                 'deg_assort', 'betweeness', 'betwVar', 'betwMax', 'eigenMax',
                 'eigenMin', 'eigenAvg', 'eigenVar', 'closeMax', 'closeMin',
                 'closeAvg', 'closeVar', 'flowMax', 'flowAvg', 'flowVar',
                 'flow_edgeMax', 'flow_edgeMin', 'flow_edgeAvg', 'flow_edgeVar',
                 'loadMax', 'loadAvg', 'loadVar', 'harmMax', 'harmMin', 'harmAvg',
                 'harmVar', 'secorderMax', 'secorderMin', 'secorderAvg', 'secorderVar',
                 'size_corona', 'size_core', 'nbr_node_types', 'egap', 'entropyStation',
                 'N', 'dens']
    feat_dic = {col_names[k]:features[k] for k in range(len(features))}
    return pd.DataFrame(feat_dic, index = [glycan])

def graph_to_string(graph, fallback = False, libr = None):
  """converts glycan graph back to IUPAC-condensed format\n
  | Arguments:
  | :-
  | graph (networkx object): glycan graph, works with most glycans. Will often not properly format repeat glycans, e.g., xyloglucan etc
  | fallback (bool): just searches for the corresponding string in df_glycan; default:False
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-
  | Returns glycan in IUPAC-condensed format (string)
  """
  if libr is None:
    libr = lib
  if fallback:
    len_dist = min_process_glycans(df_glycan.glycan.values.tolist())
    len_dist = [len(k) for k in len_dist]
    df_glycan2 = [k for k in range(len(df_glycan)) if len_dist[k] == len(graph.nodes())]
    df_glycan2 = df_glycan.iloc[df_glycan2, :].reset_index(drop = True)
    idx = np.where([compare_glycans(graph, glycan_to_nxGraph(k, libr = libr), libr = libr) for k in df_glycan2.glycan.values.tolist()])[0][0]
    glycan = df_glycan2.glycan.values.tolist()[idx]
    return glycan
  node_labels = nx.get_node_attributes(graph, 'string_labels')
  edges = graph.edges()
  branch_points = [e[1] for e in edges if abs(e[0]-e[1]) > 1]

  #note if a monosaccharide is a bona fide branch point
  skeleton = [']'+str(k) if k in branch_points else str(k) for k in node_labels.keys()]
  
  for k in range(len(skeleton)):
    #multibranch situation on reducing end
    if skeleton[k] == skeleton[-1] and graph.degree()[k] == 3:
      idx = np.where(['[' in m for m in skeleton[:k]])[0][-1]
      skeleton[idx-1] = skeleton[idx-1] + ']'
    #note whether a multibranch situation exists
    if graph.degree()[k] == 4:
      idx = np.where(['[' in m for m in skeleton[:k]])[0][-1]
      skeleton[idx-1] = skeleton[idx-1] + ']'
    #note whether a branch separates neighbors
    elif graph.degree()[k] > 2:
      skeleton[k] = ']' + skeleton[k]
    #note whether a branch starts
    elif graph.degree()[k] == 1 and k > 0:
      skeleton[k] = '[' + skeleton[k]

  #combine the skeleton, format, and map to the monosaccharides/linkages
  glycan = '('.join(skeleton)[:-1]
  glycan = re.sub('(\([^\()]*)\(', r'\1)', glycan)
  glycan = glycan.replace('[)', ')[')
  glycan = glycan.replace('])', ')]')
  while ']]' in glycan:
    glycan = glycan.replace(']]', ']')
  while '[[' in glycan:
    glycan = glycan.replace('[[', '[')
  for k,j in dict(sorted(node_labels.items(), reverse = True)).items():
    if k != 0 and k != len(node_labels)-1:
      if j[0].isdigit():
        j = '_' + j
      glycan = re.sub('([^0-9a-zA-Z\-,])%s([^0-9a-zA-Z\-,])' % str(k), r'\1%s\2' % j, glycan)
  glycan = node_labels[0]+glycan[1:]
  glycan = max(glycan[:glycan.rfind(')')+1], glycan[:glycan.rfind(']')+1]) + node_labels[len(node_labels)-1]
  glycan = glycan.replace('_', '')
  return glycan

def try_string_conversion(graph, libr = None):
  """check whether glycan graph describes a valid glycan\n
  | Arguments:
  | :-
  | graph (networkx object): glycan graph, works with branched glycans
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-
  | Returns glycan in IUPAC-condensed format (string) if glycan is valid, otherwise returns None
  """
  if libr is None:
    libr = lib
  try:
    temp = graph_to_string(graph)
    temp = glycan_to_nxGraph(temp, libr = libr)
    return graph_to_string(temp)
  except:
    return None

def largest_subgraph(glycan_a, glycan_b, libr = None):
  """find the largest common subgraph of two glycans\n
  | Arguments:
  | :-
  | glycan_a (string or networkx): glycan in IUPAC-condensed format or as networkx graph
  | glycan_b (string or networkx): glycan in IUPAC-condensed format or as networkx graph
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-  
  | Returns the largest common subgraph as a string in IUPAC-condensed; returns empty string if there is no common subgraph
  """
  if libr is None:
    libr = lib
  graph_a = ensure_graph(glycan_a, libr = libr)
  graph_b = ensure_graph(glycan_b, libr = libr)
  ismags = nx.isomorphism.ISMAGS(graph_a, graph_b,
                                 node_match = nx.algorithms.isomorphism.categorical_node_match('labels', len(libr)))
  largest_common_subgraph = list(ismags.largest_common_subgraph())
  lgs = graph_a.subgraph(list(largest_common_subgraph[0].keys()))
  if nx.is_connected(lgs):
    min_num = min(list(lgs.nodes()))
    node_dic = {k:k-min_num for k in list(lgs.nodes())}
    lgs = nx.relabel_nodes(lgs, node_dic)
    if len(list(lgs.nodes())) > 0:
      try:
        return graph_to_string(lgs)
      except:
        return graph_to_string(lgs, fallback = True, libr = libr)
    else:
      return ""
  else:
    return ""

def get_possible_topologies(glycan, libr = None):
  """creates possible glycans given a floating substituent; only works with max one floating substituent\n
  | Arguments:
  | :-
  | glycan (string or networkx): glycan in IUPAC-condensed format or as networkx graph
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-
  | Returns list of NetworkX-like glycan graphs of possible topologies
  """
  if libr is None:
    libr = lib
  if isinstance(glycan, str):
    if '{' not in glycan:
      print("This glycan already has a defined topology; please don't use this function.")
  ggraph = ensure_graph(glycan, libr = libr)
  parts = [ggraph.subgraph(c) for c in nx.connected_components(ggraph)]
  topologies = []
  for k in list(parts[-1].nodes()):
    #only add to non-reducing ends
    if parts[-1].degree[k] == 1 and k != max(list(parts[-1].nodes())):
      ggraph2 = copy.deepcopy(ggraph)
      ggraph2.add_edge(max(list(parts[0].nodes())), k)
      ggraph2 = nx.relabel_nodes(ggraph2, {list(ggraph2.nodes())[j]:j for j in list(range(len(ggraph2.nodes())))})
      topologies.append(ggraph2)
  return topologies

def possible_topology_check(glycan, glycans, libr = None):
  """checks whether glycan with floating substituent could match glycans from a list; only works with max one floating substituent\n
  | Arguments:
  | :-
  | glycan (string or networkx): glycan in IUPAC-condensed format (or as networkx graph) that has to contain a floating substituent
  | glycans (list): list of glycans in IUPAC-condensed format (or networkx graphs; should not contain floating substituents)
  | libr (list): library of monosaccharides; if you have one use it, otherwise a comprehensive lib will be used\n
  | Returns:
  | :-
  | Returns list of glycans that could match input glycan
  """
  if libr is None:
    libr = lib
  topologies = get_possible_topologies(glycan, libr = libr)
  out_glycs = []
  for g in glycans:
    ggraph = ensure_graph(g, libr = libr)
    if any([compare_glycans(t, ggraph, libr = libr) for t in topologies]):
      out_glycs.append(g)
  return out_glycs
