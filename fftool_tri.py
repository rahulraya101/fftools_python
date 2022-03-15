#!/usr/bin/env python
# fftool - generate force field parameters for molecular system
# Agilio Padua <agilio.padua@ens-lyon.fr>, version 2021/05/25
# http://perso.ens-lyon.fr/agilio.padua

# Copyright 2013 Agilio Padua
#
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import argparse
import math
import collections
import xml.etree.ElementTree as ET

# tolerances when deducing bonds and angles from input configuration
BondTol = 0.25                          # Angstrom
AngleTol = 15.0                         # degrees

kCal = 4.184                            # kJ
eV = 96.485                             # kJ/mol

# --------------------------------------

atomic_wt = {'H': 1.008, 'Li': 6.941, 'B': 10.811, 'C': 12.011,
             'N': 14.006, 'O': 15.999, 'F': 18.998, 'Ne': 20.180,
             'Na': 22.990, 'Mg': 24.305, 'Al': 26.982, 'Si':  28.086,
             'P': 30.974, 'S': 32.065, 'Cl': 35.453, 'Ar': 39.948,
             'K': 39.098, 'Ca': 40.078, 'Ti': 47.867, 'Fe': 55.845,
             'Zn': 65.38, 'Se': 78.971, 'Br': 79.904, 'Kr': 83.798,
             'Mo': 95.96, 'Ru': 101.07, 'Sn': 118.710, 'Te': 127.60,
             'I': 126.904, 'Xe': 131.293}

atomic_nr = {'H': 1, 'Li': 3, 'B': 5, 'C': 6, 'N': 7, 'O': 8, 'F': 9, 'Ne': 10,
             'Na': 11, 'Mg': 12, 'Al': 13, 'Si': 14, 'P': 15, 'S': 16,
             'Cl': 17, 'Ar': 18, 'K': 19, 'Ca': 20, 'Ti': 22, 'Fe': 26,
             'Zn': 30, 'Se': 34, 'Br': 35, 'Kr': 36, 'Mo': 42, 'Ru': 44,
             'Sn': 50, 'Te': 52, 'I': 53, 'Xe': 54}
    
def atomic_weight(name):
    if name[:2] in atomic_wt:
        return atomic_wt[name[:2]]
    elif name[0] in atomic_wt:
        return atomic_wt[name[0]]
    else:
        print('warning: unknown atomic weight for atom ' + name)
        return 0.0

def atomic_symbol(name):
    if name[:2] in atomic_wt:
        return name[:2]
    elif name[0] in atomic_wt:
        return name[0]
    else:
        print('warning: unknown symbol for atom ' + name)
        return name

def atomic_number(name):
    if name[:2] in atomic_nr:
        return atomic_nr[name[:2]]
    elif name[0] in atomic_nr:
        return atomic_nr[name[0]]
    else:
        print('warning: unknown atomic weight for atom ' + name)
        return 0

# --------------------------------------

class vec3(object):
    '''minimal 3-vector'''

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, tuple) or isinstance(x, list):
            self.x, self.y, self.z = x
        else:
            self.x = x
            self.y = y
            self.z = z

    def __getitem__(self, index):
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        elif index == 2:
            return self.z
        else:
            raise IndexError('vec3 index out of range')

    def __abs__(self):
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    
    def __add__(self, other):
        if isinstance(other, vec3):
            return vec3(self.x + other.x, self.y + other.y, self.z + other.z)
        else:
            raise TypeError('wrong type in vec3 addition')

    def __sub__(self, other):
        if isinstance(other, vec3):
            return vec3(self.x - other.x, self.y - other.y, self.z - other.z)
        else:
            raise TypeError('wrong type in vec3 subtraction')

    def __mul__(self, other): 
        if isinstance(other, vec3): # dot product
            return self.x * other.x + self.y * other.y + self.z * other.z
        else:
            return vec3(self.x * other, self.y * other, self.z * other)

    def __div__(self, other):
        return vec3(self.x / other, self.y / other, self.z / other)

    def __neg__(self):
        return vec3(-self.x, -self.y, -self.z)

    def __str__(self):
        return '( {}, {}, {} )'.format(self.x, self.y, self.z)

    def __repr__(self):
        return str(self) + ' instance at 0x' + str(hex(id(self))[2:].upper())

    def cross(self, other):
        return vec3(self.y * other.z - self.z * other.y,  
                    self.z * other.x - self.x * other.z,  
                    self.x * other.y - self.y * other.x)

    def unit(self):
        a = abs(self)
        return vec3(self.x / a, self.y / a, self.z / a)

# --------------------------------------

def indent_xml(elem, level=0, hor=' ', ver='\n'):
    '''pretty-print xml from element tree'''

    spc = ver + level * hor
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = spc + hor
        if not elem.tail or not elem.tail.strip():
            elem.tail = spc
        for elem in elem:
            indent_xml(elem, level + 1, hor, ver)
        if not elem.tail or not elem.tail.strip():
            elem.tail = spc
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = spc

# --------------------------------------
 
class atom(object):
    '''atom in a molecule or in a force field'''

    def __init__(self, name, m=0.0):
        self.name = name
        self.uname = name                 # unique name (xml, charmm)
        self.type = ''                    # atom type for bonded terms
        self.utype = ''                   # unique type (xml, charmm)
        self.ityp = -1                    # atom type index for this atom
        if m == 0.0:
            self.m = atomic_weight(self.name)
        else:
            self.m = m
        self.q = 0.0
        self.pot = ''
        self.par = []
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.bond_partners = []

    def __str__(self):
        if hasattr(self, 'type'):
            return 'atom {:5s} {:3s}  m = {:7.3f}  q = {:+7.4f}  {} {}'\
                .format(self.name, self.type, self.m, self.q, self.pot,
                str(self.par))
        else:
            return 'atom {:5s}  m = {:7.3f}'.format(self.name, self.m)

    def setpar(self, attp, q, pot, par):
        '''set atom parameters'''
        self.type = attp
        self.q = q
        self.pot = pot
        self.par = par


def dist2atoms(ati, atj, box=None):
    '''compute distance btween two atoms handling pbc'''
    dx = atj.x - ati.x
    dy = atj.y - ati.y
    dz = atj.z - ati.z
    if isinstance(box, cell):
        if box.triclinic:
            ri = [ ati.x, ati.y, ati.z ]
            rj = [ atj.x, atj.y, atj.z ]
            fi = box.ctof(ri)
            fj = box.ctof(rj)
            fd = [ fj[0] - fi[0], fj[1] - fi[1], fj[2] - fi[2] ]
            if 'x' in box.pbc:
                fd[0] -= round(fd[0])
            if 'y' in box.pbc:
                fd[1] -= round(fd[1])
            if 'z' in box.pbc:
                fd[2] -= round(fd[2])
            dx, dy, dz = box.ftoc(fd)
        else:
            if 'x' in box.pbc:
                dx -= round(dx / box.lx) * box.lx
            if 'y' in box.pbc:
                dy -= round(dy / box.ly) * box.ly
            if 'z' in box.pbc:
                dz -= round(dz / box.lz) * box.lz
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def angle3atoms(ati, atj, atk, box=None):
    '''compute angle formed by three atoms handling pbc'''
    djix = ati.x - atj.x
    djiy = ati.y - atj.y
    djiz = ati.z - atj.z    
    djkx = atk.x - atj.x
    djky = atk.y - atj.y
    djkz = atk.z - atj.z
    if isinstance(box, cell):
        if box.triclinic:
            ri = [ ati.x, ati.y, ati.z ]
            rj = [ atj.x, atj.y, atj.z ]
            rk = [ atk.x, atk.y, atk.z ]
            fi = box.ctof(ri)
            fj = box.ctof(rj)
            fk = box.ctof(rk)
            fdji = [ fi[0] - fj[0], fi[1] - fj[1], fi[2] - fj[2] ]
            fdjk = [ fk[0] - fj[0], fk[1] - fj[1], fk[2] - fj[2] ]
            if 'x' in box.pbc:
                fdji[0] -= round(fdji[0])
                fdjk[0] -= round(fdjk[0])
            if 'y' in box.pbc:
                fdji[1] -= round(fdji[1])
                fdjk[1] -= round(fdjk[1])
            if 'z' in box.pbc:
                fdji[2] -= round(fdji[2])
                fdjk[2] -= round(fdjk[2])
            djix, djiy, djiz = box.ftoc(fdji)
            djkx, djky, djkz = box.ftoc(fdjk)
        else:
            if 'x' in box.pbc:
                djix -= round(djix / box.lx) * box.lx
                djkx -= round(djkx / box.lx) * box.lx
            if 'y' in box.pbc:
                djiy -= round(djiy / box.ly) * box.ly
                djky -= round(djky / box.ly) * box.ly
            if 'z' in box.pbc:
                djiz -= round(djiz / box.lz) * box.lz
                djkz -= round(djkz / box.lz) * box.lz
    vji = vec3(djix, djiy, djiz)
    vjk = vec3(djkx, djky, djkz)
    return math.acos((vji * vjk) / (abs(vji) * abs(vjk))) * 180.0 / math.pi


class bond(object):
    '''covalent bond in a molecule or in a force field'''

    def __init__(self, i=-1, j=-1, r=0.0):
        self.i = i
        self.j = j
        self.r = r
        self.ityp = -1

    def __str__(self):
        if hasattr(self, 'name'):
            if self.i != -1:
                return 'bond {:5d} {:5d}  {}  {} {}'.format(self.i + 1,
                    self.j + 1, self.name, self.pot, str(self.par))
            else:
                return 'bond {}  {} {}'.format(self.name, self.pot,
                    str(self.par))
        else:
            return 'bond {:5d} {:5d}'.format(self.i + 1, self.j + 1)

    def setpar(self, iatp, jatp, pot, par):
        '''set bond parameters'''
        self.name = '{}-{}'.format(iatp, jatp)
        self.iatp = iatp
        self.jatp = jatp
        self.pot = pot
        self.par = par

    def seteqval(self):
        '''set bond equilibrium length'''
        if not hasattr(self, 'name'):
            raise RuntimeError('bond parameters not set')
        if self.pot == 'harm':
            self.eqval = self.par[0]
        elif self.pot == 'cons':
            self.eqval = self.par[0]
        else:
            raise ValueError('unkown bond potential ' + self.pot)

    def checkval(self, r):
        '''check if bond distance is close to force field value'''
        if not hasattr(self, 'eqval'):
            raise RuntimeError('bond equilibrium value not set')
        delta = abs(r - self.eqval)
        if delta < BondTol:
            return True
        else:
            return False


class angle(object):
    '''valence angle'''

    def __init__(self, i=-1, j=-1, k=-1, theta=0.0):
        self.i = i
        self.j = j
        self.k = k
        self.theta = theta
        self.ityp = -1

    def __str__(self):
        if hasattr(self, 'name'):
            if self.i != -1:
                return 'angle {:5d} {:5d} {:5d}  {}  {} {}'.format(
                    self.i + 1, self.j + 1, self.k + 1,
                    self.name, self.pot, str(self.par))
            else:
                return 'angle {}  {} {}'.format(self.name, self.pot,
                                                str(self.par))
        else:
            return 'angle {:5d} {:5d} {:5d}'.format(self.i + 1, self.j + 1,
                                                    self.k + 1)

    def setpar(self, iatp, jatp, katp, pot, par):
        '''set angle parameters'''
        self.name = '{0}-{1}-{2}'.format(iatp, jatp, katp)
        self.iatp = iatp
        self.jatp = jatp
        self.katp = katp
        self.pot = pot
        self.par = par

    def seteqval(self):
        '''set angle equilibrium value'''
        if not hasattr(self, 'name'):
            raise RuntimeError('angle parameters not set')
        if self.pot == 'harm':
            self.eqval = self.par[0]
        elif self.pot == 'cons':
            self.eqval = self.par[0]
        else:
            raise ValueError('unkown angle potential ' + self.pot)

    def checkval(self, th):
        '''check if angle value is close to force field value'''
        if not hasattr(self, 'eqval'):
            raise RuntimeError('angle equilibrium value not set')
        delta = abs(th - self.eqval)
        if delta < AngleTol:
            return True
        else:
            return False


class dihed(object):
    '''dihedral angle (torsion)'''

    def __init__(self, i=-1, j=-1, k=-1, l=-1, phi=0.0):
        self.i = i
        self.j = j
        self.k = k
        self.l = l
        self.phi = phi
        self.ityp = -1

    def __str__(self):
        if hasattr(self, 'name'):
            if self.i != -1:
                return 'dihedral {:5d} {:5d} {:5d} {:5d}  {}  {} {}'.format(
                    self.i + 1, self.j + 1, self.k + 1, self.l + 1,
                    self.name, self.pot, str(self.par))
            else:
                return 'dihedral {}  {} {}'.format(self.name, self.pot,
                                                str(self.par))
        else:
            return 'dihedral {:5d} {:5d} {:5d} {:5d}'.format(self.i + 1,
                    self.j + 1, self.k + 1, self.l + 1)

    def setpar(self, iatp, jatp, katp, latp, pot, par):
        '''set dihedral parameters'''
        self.name = '{}-{}-{}-{}'.format(iatp, jatp, katp, latp)
        self.iatp = iatp
        self.jatp = jatp
        self.katp = katp
        self.latp = latp
        self.pot = pot
        self.par = par


class dimpr(dihed):
    '''improper dihedral angle'''
    
    def __str__(self):
        if hasattr(self, 'name'):
            if self.i != -1:
                return 'improper {:5d} {:5d} {:5d} {:5d}  {}  {} {}'\
                    .format(self.i + 1, self.j + 1, self.k + 1, self.l + 1,
                    self.name, self.pot, str(self.par))
            else:
                return 'improper {}  {} {}'.format(self.name, self.pot,
                                                   str(self.par))  
        else:
            return 'improper {:5d} {:5d} {:5d} {:5d}'.format(self.i + 1,
                   self.j + 1, self.k + 1, self.l + 1)


# --------------------------------------

class zmat(object):
    '''z-matrix representing a molecule, read from .zmat file'''

    def __init__(self, filename):
        self.zatom = []
        self.connect = []
        self.improper = []
        
        with open(filename, 'r') as f:

            # read molecule name
            line = f.readline()
            while line.strip().startswith('#'):
                line = f.readline()
            self.name = line.strip()

            #read z-matrix
            line = f.readline()
            while line.strip().startswith('#') or line.strip() == '':
                line = f.readline()
            
            tok = line.strip().split()
            if len(tok) > 1:   # there can be line numbers
                shift = 1
            else:
                shift = 0

            variables = False
            while line and not line.strip().lower().startswith('var'):
                tok = line.strip().split()
                if len(tok) == 0:
                    break
                name = tok[shift]
                ir = ia = id = 0
                r = a = d = 0.0
                rvar = avar = dvar = ''
                if (len(tok) - shift) > 1:
                    ir = int(tok[shift+1])
                    if tok[shift+2][0].isalpha():
                        rvar = tok[shift+2]
                        variables = True
                    else:
                        r = float(tok[shift+2])
                    if (len(tok) - shift) > 3:
                        ia = int(tok[shift+3])
                        if tok[shift+4][0].isalpha():
                            avar = tok[shift+4]
                            variables = True
                        else:
                            a = float(tok[shift+4])
                        if (len(tok) - shift) > 5:
                            id = int(tok[shift+5])
                            if tok[shift+6][0].isalpha():
                                dvar = tok[shift+6]
                                variables = True
                            else:
                                d = float(tok[shift+6])
                zatom = {'name': name,
                        'ir': ir, 'rvar': rvar, 'r': r,
                        'ia': ia, 'avar': avar, 'a': a,
                        'id': id, 'dvar': dvar, 'd': d}
                self.zatom.append(zatom)
                line = f.readline()
                
            # read variables
            if variables:
                if line.strip().lower().startswith('var') or line.strip()=='':
                    line = f.readline()
                while line:
                    tok = line.strip().split('=')
                    if len(tok) < 2:
                        break
                    key = tok[0].strip()
                    val = float(tok[1])
                    for rec in self.zatom:
                        if rec['rvar'] == key:
                            rec['r'] = val
                        if rec['avar'] == key:
                            rec['a'] = val
                        if rec['dvar'] == key:
                            rec['d'] = val
                    line = f.readline()
                        
            # read connects, improper, force field file
            self.ffile = None
            self.guessconnect = False
            while line:
                if line.strip().startswith('#') or line.strip() == '':
                    line = f.readline()
                    continue
                tok = line.strip().split()
                if tok[0] == 'reconnect':
                    self.guessconnect = True
                if tok[0] == 'connect':
                    atomi = int(tok[1])
                    atomj = int(tok[2])
                    self.connect.append([atomi, atomj])
                elif tok[0] == 'improper':
                    atomi = int(tok[1])
                    atomj = int(tok[2])
                    atomk = int(tok[3])
                    atoml = int(tok[4])
                    self.improper.append([atomi, atomj, atomk, atoml])
                else:
                    self.ffile = tok[0]
                line = f.readline()
                            
    def show(self):
        '''show z-matrix object'''
        print(self.name)
        i = 0
        for rec in self.zatom:
            i += 1
            if rec['ir'] == 0:
                print('{:<3d} {:<5}'.format(i, rec['name']))
            elif rec['ia'] == 0:
                print('{:<3d} {:<5} {:3d} {:6.3f}'.format(
                      i, rec['name'], rec['ir'], rec['r']))
            elif rec['id'] == 0:
                print('{:<3d} {:<5} {:3d} {:6.3f} {:3d} {:6.1f}'.format(
                    i, rec['name'], rec['ir'], rec['r'], rec['ia'], rec['a']))
            else:
                print('{:<3d} {:<5} {:3d} {:6.3f} {:3d} {:6.1f} {:3d} {:6.1f}'\
                    .format(i, rec['name'], rec['ir'], rec['r'],
                    rec['ia'], rec['a'], rec['id'], rec['d']))
        if len(self.connect) > 0:
            print('connects')
            for c in self.connect:
                print('{:3d} ({:5}) -- {:3d} ({:5s})'.format(
                    c[0], self.zatom[c[0]-1]['name'],
                    c[1], self.zatom[c[1]-1]['name']))
        if self.ffile:
            print('force field: ' + self.ffile)


# --------------------------------------


class mol(object):
    '''molecule'''

    def __init__(self, filename, connect=True, box=None):
        self.atom = []
        self.bond = []
        self.angle = []
        self.dihed = []
        self.dimpr = []
        self.m = 0
        self.nmol = 0
        self.ffile = None
        self.ff = None
        self.topol = 'none'
        self.nbond = 0
        
        with open(filename, 'r'):
            self.filename = filename
        ext = filename.split('.')[-1].strip().lower()
        if ext == 'zmat':
            self.fromzmat(filename, connect)
        elif ext == 'mol':
            self.frommdlmol(filename, connect)
        elif ext == 'xyz':
            self.fromxyz(filename, connect, box)
        elif ext == 'pdb':
            self.frompdb(filename, connect, box)
        else:
            raise ValueError('unsupported molecule file extension')
        self.nbond = len(self.bond)

        self.setff(box)

        self.res = self.name.replace('-', '').replace('+', '')[:3]  # 3-char residue name
        self.indexatomnames()
        self.indexatomtypes()
        
    def __str__(self):
        return 'molecule {}  {:d} atoms  m = {:8.4f}'.format(self.name,
            len(self.atom), self.m)
            
    def charge(self):
        '''calculate molecule charge from atom partial charges'''
        q = 0.0
        for at in self.atom:
            q += at.q
        return q + 1.e-12

    def indexatomnames(self):
        '''set unique short atom names appending numbers to element'''
        names = []
        for at in self.atom:
            names.append(atomic_symbol(at.name))
        cnt = collections.Counter(names)
        n = dict.fromkeys(cnt, 0)
        for at in self.atom:
            for key in n:
                if at.name[0] == key:
                    n[key] += 1
                    if cnt[key] > 1:
                        s = str(n[key])
                    else:
                        s = ''
                    at.uname = at.name[0] + s
                    break

    def indexatomtypes(self):
        '''
        set unique atom types for OpenMM using residue name:
        RES-ATOM-# where # is a serial number
        '''
        names = []
        for at in self.atom:
            names.append(at.name)
        cnt = collections.Counter(names)
        n = dict.fromkeys(cnt, 0)
        for at in self.atom:
            for key in n:
                if at.name == key:
                    n[key] += 1
                    #if at.name[-1].isdigit():
                    #    if n[key] <= 26:
                    #        s = chr(ord('`') + n[key])   # lowercase
                    #    elif n[key] <= 702:
                    #        q, r = divmod(n[key] - 1, 26)
                    #        s = chr(ord('`') + q) + chr(ord('a') + r )
                    #    else:
                    #        raise RuntimeError('unable to index too many atoms '
                    #            + at.uname + ' in ' + self.name)
                    #else:
                    #    s = str(n[key])
                    #at.utype = self.name[:3] + '-' + at.name + s
                    at.utype = self.res + '-' + at.name + '-' + str(n[key])
                    break

    def fromzmat(self, filename, connect):
        '''read molecule feom z-matrix file'''

        z = zmat(filename)
        self.name = z.name
        self.guessconnect = z.guessconnect
        self.ffile = z.ffile
        for zat in z.zatom:
            self.atom.append(atom(zat['name']))
            self.m += atomic_weight(zat['name'])
        self.zmat2cart(z)
        if connect and self.ffile:          # topology only if ff defined
            if not self.guessconnect:
                for i in range(1, len(z.zatom)):
                    self.bond.append(bond(i, z.zatom[i]['ir'] - 1))
                for cn in z.connect:
                    self.bond.append(bond(cn[0] - 1, cn[1] - 1))
                self.topol = 'file'
            else:
                self.connectivity()
                self.topol = 'guess'
            for di in z.improper:                 
                self.dimpr.append(dimpr(di[0]-1, di[1]-1, di[2]-1, di[3]-1))
            self.anglesdiheds()
        return self
    
    def zmat2cart(self, z):
        '''convert z-matrix to cartesian coordinates'''

        natom = len(self.atom)    
        if natom != len(z.zatom):
            raise RuntimeError('different numbers of atoms in zmat ' + self.name)

        if natom == 0:
            return self

        # first atom at origin
        self.atom[0].x = 0.0
        self.atom[0].y = 0.0
        self.atom[0].z = 0.0
        if natom == 1:
            return self

        # second atom at distance r from first along xx
        self.atom[1].x = z.zatom[1]['r']
        self.atom[1].y = 0.0
        self.atom[1].z = 0.0
        if natom == 2:
            return self

        # third atom at distance r from ir forms angle a 3-ir-ia in plane xy
        r = z.zatom[2]['r']
        ir = z.zatom[2]['ir'] - 1
        ang = z.zatom[2]['a'] * math.pi / 180.0
        ia = z.zatom[2]['ia'] - 1

        # for this construction, the new atom is at point (x, y), atom
        # ir is at point (xr, yr) and atom ia is at point (xa, ya).
        # Theta is the angle between the vector joining ir to ia and
        # the x-axis, a' (= theta - a) is is the angle between r and
        # the x-axis. x = xa + r cos a', y = ya + r sin a'.  From the
        # dot product of a unitary vector along x with the vector from
        # ir to ia, theta can be calculated: cos theta = (xa - xr) /
        # sqrt((xa - xr)^2 + (ya - yr)^2).  If atom ia is in third or
        # forth quadrant relative to atom ir, ya - yr < 0, then theta
        # = 2 pi - theta. */
        delx = self.atom[ia].x - self.atom[ir].x
        dely = self.atom[ia].y - self.atom[ir].y
        theta = math.acos(delx / math.sqrt(delx*delx + dely*dely))
        if dely < 0.0:
            theta = 2 * math.pi - theta
        ang = theta - ang
        self.atom[2].x = self.atom[ir].x + r * math.cos(ang)
        self.atom[2].y = self.atom[ir].y + r * math.sin(ang)
        self.atom[2].z = 0.0
        if natom == 3:
            return self
        
        # nth atom at distance r from atom ir forms angle a at 3-ir-ia
        # and dihedral angle between planes 3-ir-ia and ir-ia-id
        for i in range(3, natom):
            r = z.zatom[i]['r']
            ir = z.zatom[i]['ir'] - 1
            ang = z.zatom[i]['a'] * math.pi / 180.0
            ia = z.zatom[i]['ia'] - 1
            dih = z.zatom[i]['d'] * math.pi / 180.0
            id = z.zatom[i]['id'] - 1

            # for this construction the new atom is at point A, atom ir is
            # at B, atom ia at C and atom id at D.  Point a is the
            # projection of A onto the plane BCD.  Point b is the
            # projection of A along the direction BC (the line defining
            # the dihedral angle between planes ABC and BCD). n = CD x BC
            # / |CD x BC| is the unit vector normal to the plane BCD. m =
            # BC x n / |BC x n| is the unit vector on the plane BCD normal
            # to the direction BC.
            #                               
            #                               .'A
            #                 ------------.' /.-----------------
            #                /           b /  .               /
            #               /           ./    .              /
            #              /           B......a      ^      /
            #             /           /              |n    /
            #            /           /                    /
            #           /           C                    /
            #          /             \                  /
            #         /               \                /
            #        /plane BCD        D              /
            #       ----------------------------------
            #
            #                    A              C------B...b
            #                   /.             /        .  .
            #                  / .            /    |m    . .
            #                 /  .           /     V      ..
            #         C------B...b          D              a
            #
            
            BA = r
            vB = vec3(self.atom[ir].x, self.atom[ir].y, self.atom[ir].z)
            vC = vec3(self.atom[ia].x, self.atom[ia].y, self.atom[ia].z)
            vD = vec3(self.atom[id].x, self.atom[id].y, self.atom[id].z)

            vBC = vC - vB
            vCD = vD - vC
            
            BC = abs(vBC)
            bB = BA * math.cos(ang)
            bA = BA * math.sin(ang)
            aA = bA * math.sin(dih)
            ba = bA * math.cos(dih)

            vb = vC - vBC * ((BC - bB) / BC)
            vn = (vCD.cross(vBC)).unit()
            vm = (vBC.cross(vn)).unit()
            va = vb + vm * ba
            vA = va + vn * aA

            self.atom[i].x = vA.x
            self.atom[i].y = vA.y
            self.atom[i].z = vA.z
        return self
    
    def frommdlmol(self, filename, connect):
        '''reda molecule from MDL mol file'''

        with open(filename, 'r') as f:
            tok = f.readline().strip().split()
            self.name = tok[0]            # molecule name
            self.guessconnect = False
            if len(tok) > 1:              # and eventually ff file
                self.ffile = tok[1]
                if len(tok) > 2:
                    if tok[2].startswith('rec'):
                        self.guessconnect = True
            else:
                self.ffile = None
            f.readline()                  # program/date info
            line = f.readline().strip()   # comment (eventually ff file)
            if line and not line.startswith('#') and not self.ffile:
                tok = line.split()
                self.ffile = tok[0]
                if len(tok) > 1:
                    if tok[1].startswith('rec'):
                        self.guessconnect = True
            line = f.readline()           # counts line
            natom = int(line[0:3])
            nbond = int(line[3:6])
            self.atom = [None] * natom
            for i in range(natom):
                tok = f.readline().strip().split()
                self.atom[i] = atom(tok[3])
                self.atom[i].x = float(tok[0])
                self.atom[i].y = float(tok[1])
                self.atom[i].z = float(tok[2])
            if connect and self.ffile:      # topology only if ff defined
                if not self.guessconnect:
                    self.bond = [None] * nbond
                    for k in range(nbond):
                        line = f.readline()
                        i = int(line[0:3]) - 1
                        j = int(line[3:6]) - 1
                        self.bond[k] = bond(i, j)
                    self.topol = 'file'
                else:
                    self.connectivity()
                    self.topol = 'guess'
                self.anglesdiheds()
        return self
                                
    def fromxyz(self, filename, connect=False, box=None):
        '''read molecule from xyz file'''

        with open(filename, 'r') as f:
            natom = int(f.readline().strip())
            self.atom = [None] * natom
            tok = f.readline().strip().split()
            self.name = tok[0]            # molecule name
            if len(tok) > 1:              # and eventually ff file
                self.ffile = tok[-1]
            else:
                self.ffile = None
            for i in range(natom):
                tok = f.readline().strip().split()
                self.atom[i] = atom(tok[0])
                self.atom[i].x = float(tok[1])
                self.atom[i].y = float(tok[2])
                self.atom[i].z = float(tok[3])
        if connect and self.ffile:
            self.connectivity(box)
            self.anglesdiheds()
            if isinstance(box, cell) and box.pbc:
                self.topol = 'pbc'
            else:
                self.topol = 'guess'
        return self

    def frompdb(self, filename, connect = False, box = None):
        '''read molecule from pdb file'''

        with open(filename, 'r') as f:
            self.name = ''
            self.ffile = None
            line = f.readline()
            while not (line.startswith('HETATM') or line.startswith('ATOM  ')):
                if line.startswith('COMPND'):
                    tok = line.strip().split()
                    self.name = tok[1]
                    if len(tok) >= 3: 
                        self.ffile = tok[2]
                line = f.readline()
            self.atom = []
            while line[0:6] == 'HETATM' or line[0:6] == 'ATOM  ':
                atname = line[12:16].strip()
                self.atom.append(atom(atname))
                self.atom[-1].x = float(line[30:38])
                self.atom[-1].y = float(line[38:46])
                self.atom[-1].z = float(line[46:54])
                line = f.readline()
        if connect and self.ffile:           # TODO read conect
            self.connectivity(box)
            self.anglesdiheds()
            if isinstance(box, cell) and box.pbc:
                self.topol = 'pbc'
            else:
                self.topol = 'guess'
        return self
    
    def connectivity(self, box=None):    
        '''determine connectivity from bond distances in force field'''

        self.ff = forcefield(self.ffile)
        error = False
        for at in self.atom:
            found = False
            for ffat in self.ff.atom:     
                if at.name == ffat.name:
                    at.type = ffat.type
                    found = True
            if not found:
                print('  error in ' + self.name + ': no parameters for atom ' +
                      at.name)
                error = True
        if error:
            raise RuntimeError

        natom = len(self.atom)
        for i in range(0, natom-1):
            for j in range(i+1, natom):
                r = dist2atoms(self.atom[i], self.atom[j], box)
                names = ['{}-{}'.format(self.atom[i].type, self.atom[j].type),
                         '{}-{}'.format(self.atom[j].type, self.atom[i].type)]
                for ffbd in self.ff.bond:
                    nameff = '{}-{}'.format(ffbd.iatp, ffbd.jatp)
                    if nameff in names:
                        if ffbd.checkval(r):
                            self.bond.append(bond(i, j))
                                        
    def anglesdiheds(self):
        '''identify angles and dihedrals based on bond connectivity'''
                 
        natom = len(self.atom)
        nbond = len(self.bond)

        # set up bond partners so that we can build 1-4 exclusion list easily
        for bd in self.bond:
            self.atom[bd.i].bond_partners.append(bd.j)
            self.atom[bd.j].bond_partners.append(bd.i)

        # identify valence angles
        for i in range(natom):  # find neighbour atoms to each atom i
            nb = 0
            neib = []
            for bd in self.bond:          
                if i == bd.i:
                    neib.append(bd.j)
                    nb += 1
                elif i == bd.j:
                    neib.append(bd.i)
                    nb += 1
            for k in range(nb - 1):
                for l in range(k + 1, nb):
                    self.angle.append(angle(neib[k], i, neib[l]))

        # identify dihedral angles
        for k in range(nbond): # find bonds around non-terminal bonds
            for l in range(nbond):
                if l == k:
                    continue
                if self.bond[l].i == self.bond[k].i:
                    for j in range(nbond):
                        if j == k or j == l:
                            continue
                        if self.bond[j].i == self.bond[k].j:
                            self.dihed.append(dihed(self.bond[l].j,
                                                    self.bond[k].i,
                                                    self.bond[k].j,
                                                    self.bond[j].j))
                        elif self.bond[j].j == self.bond[k].j:
                            self.dihed.append(dihed(self.bond[l].j,
                                                    self.bond[k].i,
                                                    self.bond[k].j,
                                                    self.bond[j].i))
                elif self.bond[l].j == self.bond[k].i:
                    for j in range(nbond):
                        if j == k or j == l:
                            continue
                        if self.bond[j].i == self.bond[k].j:
                            self.dihed.append(dihed(self.bond[l].i,
                                                    self.bond[k].i,
                                                    self.bond[k].j,
                                                    self.bond[j].j))
                        elif self.bond[j].j == self.bond[k].j:
                            self.dihed.append(dihed(self.bond[l].i,
                                                    self.bond[k].i,
                                                    self.bond[k].j,
                                                    self.bond[j].i))

        # identify possible impropers if not supplied with z-matrix
        if not self.dimpr:
            for i in range(natom):  # find atoms with 3 neighbours
                nb = 0
                neib = []
                for bd in self.bond:          
                    if i == bd.i:
                        neib.append(bd.j)
                        nb += 1
                    elif i == bd.j:
                        neib.append(bd.i)
                        nb += 1
                if nb == 3:
                    self.dimpr.append(dimpr(neib[0], neib[1], i, neib[2]))
        
        return self
    
    def setff(self, box=None):
        '''set force field parameters'''
        
        if not self.ffile:
            print('  warning: no force field for ' + self.name)
            for at in self.atom:
                at.setpar(at.name, 0.0, 'lj', [0.0, 0.0])
            return self
        
        if not self.ff:
            self.ff = forcefield(self.ffile)

        error = False
        # identify atom types and set parameters
        for at in self.atom:
            found = False
            for ffat in self.ff.atom:     
                if at.name == ffat.name:
                    if found:
                        print('  warning: duplicate atom ' + at.name + ' in ' +
                              self.ffile)
                    at.setpar(ffat.type, ffat.q, ffat.pot, ffat.par)
                    at.m = ffat.m
                    found = True
            if not found:
                print('  error in ' + self.name + ': no parameters for atom ' +
                      at.name)
                error = True
        if error:
            raise RuntimeError
            
        # identify bonded terms and set parameters
        for bd in self.bond:
            ti = self.atom[bd.i].type
            tj = self.atom[bd.j].type
            names = [ '{}-{}'.format(ti, tj), '{}-{}'.format(tj, ti) ]
            r = dist2atoms(self.atom[bd.i], self.atom[bd.j], box)
            found = False
            for ffbd in self.ff.bond:
                nameff = '{}-{}'.format(ffbd.iatp, ffbd.jatp)
                if nameff in names:
                    bd.setpar(ffbd.iatp, ffbd.jatp, ffbd.pot, ffbd.par)
                    if not ffbd.checkval(r):
                        print('  warning: {} bond {} {:d}-{:d} '\
                            'length {:7.3f}'.format(self.name, bd.name,
                            bd.i + 1, bd.j + 1, r))
                    if found:
                        print('  warning: duplicate bond ' + bd.name + ' in ' +
                              self.ffile)
                    found = True
            if not found:
                print('  error in ' + self.name + ': no parameters for bond ' +
                      names[0])
                error = True
        if error:
            raise RuntimeError

        anmiss = []
        dhmiss = []
        dimiss = []

        toremove = []
        for an in self.angle:
            ti = self.atom[an.i].type
            tj = self.atom[an.j].type
            tk = self.atom[an.k].type
            names = [ '{}-{}-{}'.format(ti, tj, tk),
                      '{}-{}-{}'.format(tk, tj, ti) ]
            th = angle3atoms(self.atom[an.i], self.atom[an.j], self.atom[an.k],
                             box)
            found = False
            check = True
            for ffan in self.ff.angle:
                nameff = '{}-{}-{}'.format(ffan.iatp, ffan.jatp, ffan.katp)
                if nameff in names:
                    an.setpar(ffan.iatp, ffan.jatp, ffan.katp,
                              ffan.pot, ffan.par)                        
                    if not ffan.checkval(th):
                        check = False
                    if found:
                        print('  warning: duplicate angle {} in {}'.format(
                            an.name, self.ffile))
                    found = True
            if not check:
                toremove.append(an)
                print('  warning: {} angle {} {:d}-{:d}-{:d} {:.2f} '\
                    'removed'.format(self.name, an.name,
                    an.i+1, an.j+1, an.k+1, th))
            if not found:
                toremove.append(an)
                if names[0] not in anmiss:
                    anmiss.append(names[0])
        for an in toremove:
            self.angle.remove(an)

        toremove = []
        for dh in self.dihed:
            ti = self.atom[dh.i].type
            tj = self.atom[dh.j].type
            tk = self.atom[dh.k].type
            tl = self.atom[dh.l].type
            names = [ '{}-{}-{}-{}'.format(ti, tj, tk, tl),
                      '{}-{}-{}-{}'.format(tl, tk, tj, ti) ]
            found = False
            for ffdh in self.ff.dihed:
                nameff = '{}-{}-{}-{}'.format(ffdh.iatp, ffdh.jatp, ffdh.katp,
                    ffdh.latp)
                if nameff in names:
                    dh.setpar(ffdh.iatp, ffdh.jatp, ffdh.katp, ffdh.latp,
                              ffdh.pot, ffdh.par)
                    if found:
                        print('  warning: duplicate dihedral {} in {}'.format(
                            dh.name, self.ffile))
                    found = True
            if not found:
                toremove.append(dh)
                if names[0] not in dhmiss:
                    dhmiss.append(names[0])
        for dh in toremove:
            self.dihed.remove(dh)
        
        toremove = []
        for di in self.dimpr:
            ti = self.atom[di.i].type
            tj = self.atom[di.j].type
            tk = self.atom[di.k].type
            tl = self.atom[di.l].type
            names = [ '{}-{}-{}-{}'.format(ti, tj, tk, tl),
                      '{}-{}-{}-{}'.format(tj, ti, tk, tl),
                      '{}-{}-{}-{}'.format(ti, tl, tk, tj),
                      '{}-{}-{}-{}'.format(tl, ti, tk, tj),
                      '{}-{}-{}-{}'.format(tj, tl, tk, ti),
                      '{}-{}-{}-{}'.format(tl, tj, tk, ti) ]
            found = False
            for ffdi in self.ff.dimpr:
                nameff = '{}-{}-{}-{}'.format(ffdi.iatp, ffdi.jatp, ffdi.katp,
                    ffdi.latp)
                if nameff in names:
                    # sort atom numbering according to impropers in ff
                    if nameff == names[1] and tj != ti:
                        di.i, di.j = di.j, di.i
                    elif nameff == names[2] and tl != tj:
                        di.j, di.l = di.l, di.j
                    elif nameff == names[3]:
                        if tl != tj:
                            di.j, di.l = di.l, di.j
                        if tj != ti:
                            di.i, di.j = di.j, di.i
                    elif nameff == names[4]:
                        if tl != ti:
                            di.i, di.l = di.l, di.i
                        if tj != ti:
                            di.i, di.j = di.j, di.i
                    elif nameff == names[5] and tl != ti:
                        di.i, di.l = di.l, di.i
                    di.setpar(ffdi.iatp, ffdi.jatp, ffdi.katp, ffdi.latp,
                              ffdi.pot, ffdi.par)
                    if found:
                        print('  warning: duplicate improper {} in {}'.format(
                            di.name, self.ffile))
                    found = True
            if not found:
                toremove.append(di)
                if names[0] not in dimiss:
                    dimiss.append(names[0])
        for di in toremove:
            self.dimpr.remove(di)

        if len(anmiss) or len(dhmiss) or len(dimiss): 
            print('  warning: missing force field parameters')
            for s in anmiss:
                print('    angle type ' + s)
            for s in dhmiss:
                print('    dihedral type ' + s)
            for s in dimiss:
                print('    improper type ' + s)

    def show(self):
        print('{}: {:d} molecules'.format(self.name, self.nmol))
        print('{:d} atoms'.format(len(self.atom)))
        n = 0
        for at in self.atom:
            n += 1
            print('{:5d} '.format(n) + str(at))
        print('{:d} bonds'.format(len(self.bond)))
        for bd in self.bond:
            print(bd)
        print('{:d} angles'.format(len(self.angle)))
        for an in self.angle:
            print(an)
        print('{:d} dihedrals'.format(len(self.dihed)))
        for dh in self.dihed:
            print(dh)
        print('{:d} improper'.format(len(self.dimpr)))
        for di in self.dimpr:
            print(di)
        if self.ffile:
            print('field: ' + self.ffile)

    def showxyz(self, symbol = False):
        print(len(self.atom))
        if self.ffile:
            print(self.name + ' ' + self.ffile)
        else:
            print(self.name)
        for at in self.atom:
            if symbol:
                atname = atomic_symbol(at.name)
            else:
                atname = at.name
            print('{:5s} {:15.6f} {:15.6f} {:15.6f}'.format(atname,
                at.x, at.y, at.z))

    def writexyz(self, symbol = True):
        outfile = (self.filename).rsplit('.', 1)[0] + '_pack.xyz'
        with open(outfile, 'w') as f:
            f.write(str(len(self.atom)) + '\n')
            if self.ffile:
                f.write(self.name + ' ' + self.ffile + '\n')
            else:
                f.write(self.name + '\n')
            for at in self.atom:
                if symbol:
                    atname = atomic_symbol(at.name)
                else:
                    atname = at.name
                f.write('{:5s} {:15.6f} {:15.6f} {:15.6f}\n'.format(
                    atname, at.x, at.y, at.z))

    def showpdb(self):
        print('COMPND    ' + self.name)
        if self.ffile:
            print('REMARK    ' + self.ffile)
        i = 1
        for at in self.atom:
            print('HETATM{0:5d} {1:4s} {2:3s}  {3:4d}    '\
                  '{4:8.3f}{5:8.3f}{6:8.3f}  1.00  0.00'\
                  '          {7:2s}'.format(i, at.name,
                  self.name[:3], 1, at.x, at.y, at.z,
                  atomic_symbol(at.name)))
            i += 1
        print('END')

    def writepdb(self):
        outfile = (self.filename).rsplit('.', 1)[0] + '.pdb'
        with open(outfile, 'w') as f:
            f.write('COMPND    ' + self.name + '\n')
            if self.ffile:
                f.write('REMARK    ' + self.ffile + '\n')
            i = 1
            for at in self.atom:
                if len(at.name) > 4:
                    print('warning: atom name ' + at.name +
                        ' too long for pdb in ' + self.name)
                f.write('HETATM{0:5d} {1:4s} {2:3s}  {3:4d}    '\
                        '{4:8.3f}{5:8.3f}{6:8.3f}  1.00  0.00'\
                        '          {7:>2s}\n'.format(i, at.name[:4],
                        self.name[:3], 1, at.x, at.y, at.z,
                        atomic_symbol(at.name)))
                i += 1
            f.write('END\n')              # TODO write conect


# --------------------------------------


class forcefield(object):
    '''force field parameter database'''

    def __init__(self, filename):
        self.filename = filename
        self.atom = []
        self.bond = []
        self.angle = []
        self.dihed = []
        self.dimpr = []

        i = ib = ia = ih = im = 0
        for line in open(filename, 'r'):
            if line.startswith('#') or line.strip() == '':
                continue
        
            if line.lower().startswith('atom'):
                section = 'atoms'
                continue
            elif line.lower().startswith('bond'):
                section = 'bonds'
                continue
            elif line.lower().startswith('angl'):
                section = 'angles'
                continue
            elif line.lower().startswith('dihe'):
                section = 'dihedrals'
                continue
            elif line.lower().startswith('impro'):
                section = 'improper'
                continue
            tok = line.strip().split()
            if section == 'atoms':
                name = tok[0]
                attp = tok[1]
                m = float(tok[2])
                q = float(tok[3])
                pot = tok[4]
                par = [float(p) for p in tok[5:]]
                self.atom.append(atom(name, m))
                self.atom[i].setpar(attp, q, pot, par)
                i += 1
            elif section == 'bonds':
                iatp = tok[0]
                jatp = tok[1]
                pot = tok[2]
                par = [float(p) for p in tok[3:]]
                self.bond.append(bond())
                self.bond[ib].setpar(iatp, jatp, pot, par)
                ib += 1
            elif section == 'angles':
                iatp = tok[0]
                jatp = tok[1]
                katp = tok[2]
                pot = tok[3]
                par = [float(p) for p in tok[4:]]
                self.angle.append(angle())
                self.angle[ia].setpar(iatp, jatp, katp, pot, par)
                ia += 1
            elif section == 'dihedrals':
                iatp = tok[0]
                jatp = tok[1]
                katp = tok[2]
                latp = tok[3]
                pot = tok[4]
                par = [float(p) for p in tok[5:]]
                self.dihed.append(dihed())
                self.dihed[ih].setpar(iatp, jatp, katp, latp, pot, par)
                ih += 1
            elif section == 'improper':
                iatp = tok[0]
                jatp = tok[1]
                katp = tok[2]
                latp = tok[3]
                pot = tok[4]
                par = [float(p) for p in tok[5:]]
                self.dimpr.append(dimpr())
                self.dimpr[im].setpar(iatp, jatp, katp, latp, pot, par)
                im += 1
                        
        for bn in self.bond:
            bn.seteqval()
        for an in self.angle:
            an.seteqval()

    def show(self):
        print(self.filename)
        for at in self.atom:
            print(at)
        for bd in self.bond:
            print(bd)
        for an in self.angle:
            print(an)
        for dh in self.dihed:
            print(dh)
        for di in self.dimpr:
            print(di)


class vdw(object):
    '''van der Waals interaction'''        
    
    def __init__(self, iat, jat, mix='g'):
        self.i = iat.name
        self.j = jat.name
        self.iatp = iat.type
        self.jatp = jat.type
        self.ityp = iat.ityp
        self.jtyp = jat.ityp
        
        if iat.pot != jat.pot:
            raise RuntimeError('vdw with incompatible potential types ' +
              self.i + ' ' + self.j)

        self.pot = iat.pot

        if len(iat.par) != len(jat.par):
            raise RuntimeError('vdw with different lengths in parameter '\
                  'lists ' + self.i + ' ' + self.j)

        if self.pot == 'lj':
            if iat.name == jat.name:
                self.par = iat.par
            else:
                self.par = [0.0, 0.0]
                if mix == 'g':
                    self.par[0] = math.sqrt(iat.par[0] * jat.par[0])
                else:
                    self.par[0] = (iat.par[0] + jat.par[0]) / 2.
                self.par[1] = math.sqrt(iat.par[1] * jat.par[1])
                
    def __str__(self):
        return 'vdw {:2s} {:2s}  {} {}'.format(self.i, self.j, self.pot,
            str(self.par))


# --------------------------------------


class cell(object):
    '''Simulation cell/box, cubic, orthorhombic, monoclinic or triclinic'''

    def __init__(self, a, b=0.0, c=0.0, alpha=90.0, beta=90.0, gamma=90.0,
                 pbc='', center=False):
        self.a = a
        if b == 0.0:
            self.b = a
        else:
            self.b = b
        if c == 0.0:
            self.c = a
        else:
            self.c = c
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        if alpha != 90.0 or beta != 90.0 or gamma != 90.0:
            self.triclinic = True
        else:
            self.triclinic = False

        self.pbc = pbc                    # 'x', 'xy', 'xyz', etc.
        self.center = center
        
        NDIG = 14
        ca = round(math.cos(alpha * math.pi/180.0), NDIG)
        cb = round(math.cos(beta  * math.pi/180.0), NDIG)
        cg = round(math.cos(gamma * math.pi/180.0), NDIG)
        sg = round(math.sin(gamma * math.pi/180.0), NDIG)

        self.vol = v = a*b*c*math.sqrt(1 - ca*ca - cb*cb - cg*cg + 2*ca*cb*cg)

        # to convert between cartesian and fractional coords
        self.ftocmat = [[   a, b*cg, c*cb              ],
                        [ 0.0, b*sg, c*(ca - cb*cg)/sg ],
                        [ 0.0,  0.0, v/(a*b*sg)        ]]
        self.ctofmat = [[ 1.0/a, -cg/(a*sg), b*c*(ca*cg - cb)/(v*sg) ],
                        [   0.0, 1.0/(b*sg), a*c*(cb*cg - ca)/(v*sg) ],
                        [   0.0,        0.0, a*b*sg/v                ]]

        # box sizes and tilt factors
        self.lx = a
        self.xy = b*cg
        self.xz = c*cb
        # self.ly = math.sqrt(b*b - self.xy*self.xy)
        # self.yz = (b*ca - self.xy*self.xz)/self.ly
        # self.lz = math.sqrt(c*c - self.xz*self.xz - self.yz*self.yz)
        self.ly = b*sg
        self.yz = c*(ca - cb*cg)/sg
        self.lz = v/(a*b*sg)

    def ftoc(self, x):
        '''fractional to cartesian coordinates'''
        return [ sum(a*b for a,b in zip(row, x)) for row in self.ftocmat ]

    def ctof(self, x):
        '''cartesian to fractional coordinates'''
        return [ sum(a*b for a,b in zip(row, x)) for row in self.ctofmat ]


class plane():
    '''Plane passing through 3 points. p, q, r vec3 objects.'''

    def __init__(self, p, q, r):
        u = q - p
        v = r - p
        w = u.cross(v)
        self.a = w.x
        self.b = w.y
        self.c = w.z
        self.d = w * p

    def __str__(self):
        return '{:.4f} {:.4f} {:.4f} {:.4f}'.format(
            self.a, self.b, self.c, self.d)


# --------------------------------------


class system(object):
    '''Molecular system to be simulated'''

    def __init__(self, spec, box, mix='g'):
        self.spec = spec                     # molecular species
        self.box = box

        self.attype = []                     # atom types
        self.bdtype = []                     # bond types
        self.antype = []                     # angle types
        self.dhtype = []                     # dihedral types
        self.ditype = []                     # improper types
        self.vdw = []

        # build lists of different atom and bonded term types in the system
        for sp in self.spec:
            self.build_type_list(sp.atom, self.attype)
            self.build_type_list(sp.bond, self.bdtype)
            self.build_type_list(sp.angle, self.antype)
            self.build_type_list(sp.dihed, self.dhtype)
            self.build_type_list(sp.dimpr, self.ditype)

        # assign the type index for all atoms and bonded terms in the system
        for sp in self.spec:
            self.assign_type_index(sp.atom, self.attype)
            self.assign_type_index(sp.bond, self.bdtype)
            self.assign_type_index(sp.angle, self.antype)
            self.assign_type_index(sp.dihed, self.dhtype)
            self.assign_type_index(sp.dimpr, self.ditype)

        # set non-bonded parameters for all i-j type pairs
        nattypes = len(self.attype)
        for i in range(nattypes):
            for j in range(i, nattypes):
                self.vdw.append(vdw(self.attype[i], self.attype[j], mix))

    def build_type_list(self, term, termtype):
        '''build a list of atom or bonded term types'''        
        for a in term:
            found = False
            for b in termtype:
                if a.name == b.name:
                    found = True
            if not found:
                termtype.append(a)

    def assign_type_index(self, term, termtype):
        '''assign numbers to the ityp attribute in atoms or bonded terms'''
        ntypes = len(termtype)
        for a in term:
            for i in range(ntypes):
                if a.name == termtype[i].name:
                    a.ityp = termtype[i].ityp = i
                    break       

    def show(self):
        for sp in self.spec:
            print('{}  {:d} molecules, force field {}'.format(sp.name,
                sp.nmol, sp.ffile))
            for at in sp.atom:
                print(at)
            for bd in sp.bond:
                print(bd)
            for an in sp.angle:
                print(an)
            for dh in sp.dihed:
                print(dh)
            for di in sp.dimpr:
                print(di)
        for nb in self.vdw:
            print(nb)

    def writepackmol(self, packfile, outfile, tol=2.5, d=0.0):
        with open(packfile, 'w') as f:
            f.write('# created by fftool\n')
            f.write('tolerance {:3.1f}\n'.format(tol))
            f.write('filetype xyz\n')
            f.write('output {}\n'.format(outfile))
            for sp in self.spec:
                xyzfile = (sp.filename).rsplit('.', 1)[0] + '_pack.xyz'
                f.write('\nstructure {}\n'.format(xyzfile))
                f.write('  number {}\n'.format(sp.nmol))
                if self.box.triclinic:
                    o = vec3(0.0, 0.0, 0.0)
                    p = vec3(self.box.lx, 0.0, 0.0)
                    q = vec3(self.box.xy, self.box.ly, 0.0)
                    r = vec3(self.box.xz, self.box.yz, self.box.lz)
                    s = p + r
                    t = q + r
                    # u = s + q
                    v = p + q
                    back = plane(o, p, q)
                    front = plane(r, s, t)
                    bottom = plane(o, r, p)
                    top = plane(q, t, v)
                    left = plane(o, q, r)
                    right = plane(p, v, s)
                    f.write('  over plane {}\n'.format(back))
                    f.write('  below plane {}\n'.format(front))
                    f.write('  over plane {}\n'.format(bottom))
                    f.write('  below plane {}\n'.format(top))
                    f.write('  over plane {}\n'.format(left))
                    f.write('  below plane {}\n'.format(right))
                else:
                    if self.box.center:
                        f.write('  inside box {:.4f} {:.4f} {:.4f} {:.4f}'
                                ' {:.4f} {:.4f}\n'.format(
                                -self.box.a / 2.0 + d,
                                -self.box.b / 2.0 + d,
                                -self.box.c / 2.0 + d,
                                 self.box.a / 2.0 - d,
                                 self.box.b / 2.0 - d,
                                 self.box.c / 2.0 - d))
                    else:
                        f.write('  inside box {:.4f} {:.4f} {:.4f} {:.4f}'
                                ' {:.4f} {:.4f}\n'.format(d, d, d,
                            self.box.a - d, self.box.b - d, self.box.c - d))
                f.write('end structure\n')

    def readcoords(self, filename):
        with open(filename, 'r') as f:
            self.natom = int(f.readline().strip())
            self.x = [0.0] * self.natom
            self.y = [0.0] * self.natom
            self.z = [0.0] * self.natom
            tok = f.readline().strip().split()
            self.title = tok[0]
            for i in range(self.natom):
                tok = f.readline().strip().split()
                self.x[i] = float(tok[1])
                self.y[i] = float(tok[2])
                self.z[i] = float(tok[3])
            
    def writelmp(self, mix='g', allpairs=False, units='r'):
        natom = nbond = nangle = ndihed = 0
        for sp in self.spec:
            natom += sp.nmol * len(sp.atom)
            nbond += sp.nmol * len(sp.bond)
            nangle += sp.nmol * len(sp.angle)
            ndihed += sp.nmol * (len(sp.dihed) + len(sp.dimpr))
        
        with open('in.lmp', 'w') as f:
            f.write('# created by fftool\n\n')
            if units == 'r':
                f.write('units real\n')
                ecnv = kCal
            elif units == 'm':
                f.write('units metal\n')
                ecnv = eV
            else:
                raise ValueError('unknown units for lammps files')
                
            f.write('boundary p p p\n\n')

            f.write('atom_style full\n')
            if nbond:
                f.write('bond_style harmonic\n')
            if nangle:
                f.write('angle_style harmonic\n')
            if ndihed:
                f.write('dihedral_style opls\n')
            f.write('\n')
            
            f.write('special_bonds lj/coul 0.0 0.0 0.5\n\n')

            f.write('# remove hybrid if not necessary\n')
            f.write('pair_style hybrid lj/cut/coul/long 12.0 12.0\n')
            if not allpairs:
                if mix == 'g':
                    f.write('pair_modify mix geometric tail yes\n')
                else:
                    f.write('pair_modify mix arithmetic tail yes\n')
                f.write('kspace_style pppm 1.0e-5\n\n')

                f.write('read_data data.lmp\n')
                f.write('# read_restart restart1.lmp\n\n')

                f.write('# remove pair style if not using hybrid\n')
                for att in self.attype:
                    f.write('pair_coeff {:4d} {:4d} {} {:12.6f} {:12.6f}  '\
                        '# {} {}\n'.format(
                        att.ityp + 1, att.ityp + 1, 'lj/cut/coul/long',
                        att.par[1] / ecnv, att.par[0], att.name, att.name))
            else:
                f.write('pair_modify tail yes\n')
                f.write('kspace_style pppm 1.0e-5\n\n')

                f.write('read_data data.lmp\n\n')

                if len(self.vdw) <= 12:
                    for nb in self.vdw:
                        f.write('pair_coeff {:4d} {:4d} {} {:12.6f} {:12.6f}'\
                            '  # {} {}\n'.format(
                            nb.ityp + 1, nb.jtyp + 1, 'lj/cut/coul/long',
                            nb.par[1] / ecnv, nb.par[0], nb.i, nb.j))
                else:
                    with open('pair.lmp', 'w') as fp:
                        for nb in self.vdw:
                            fp.write('pair_coeff {:4d} {:4d} {} {:12.6f} '\
                                '{:12.6f}  # {} {}\n'.format(
                                    nb.ityp + 1, nb.jtyp + 1,
                                    'lj/cut/coul/long',
                                    nb.par[1] / ecnv, nb.par[0], nb.i, nb.j))
                    f.write('include pair.lmp\n')
            f.write('\n')

            f.write('# minimize 1.0e-4 1.0e-6 100 1000\n')
            f.write('# reset_timestep 0\n\n')
            
            shakebd = shakean = False
            for bdt in self.bdtype:
                if bdt.pot == 'cons':
                    shakebd = True
            for ant in self.antype:
                if ant.pot == 'cons':
                    shakean = True
            if shakebd or shakean:
                f.write('fix SHAKE all shake 0.0001 20 0')
                if shakebd:
                    f.write(' b')
                    for bdt in self.bdtype:
                        if bdt.pot == 'cons':
                            f.write(' {:d}'.format(bdt.ityp + 1))
                if shakean:
                    f.write(' a')
                    for ant in self.antype:
                        if ant.pot == 'cons':
                            f.write(' {:d}'.format(ant.ityp + 1))
                f.write('\n\n')

            f.write('neighbor 2.0 bin\n')
            f.write('# neigh_modify delay 0 every 1 check yes\n\n')

            if units == 'r':
                f.write('timestep 1.0\n\n')
            elif units == 'm':
                f.write('timestep 0.001\n\n')
                
            f.write('variable TK equal 300.0\n')
            f.write('variable PBAR equal 1.0\n\n')

            f.write('velocity all create ${TK} 12345\n\n')

            f.write('fix TPSTAT all npt temp ${TK} ${TK} 100 '\
                    'iso ${PBAR} ${PBAR} 1000\n\n')

            f.write('thermo_style custom step cpu etotal ke pe '\
                    'evdwl ecoul elong temp press vol density\n')
            f.write('thermo 1000\n\n')
            
            f.write('dump TRAJ all custom 1000 dump.lammpstrj '\
                     'id mol type element q xu yu zu\n')
            f.write('dump_modify TRAJ element')
            for att in self.attype:
                f.write(' ' + atomic_symbol(att.name))
            f.write('\n\n')

            f.write('variable vinst equal vol\n')
            f.write('fix VAVG all ave/time 10 1000 50000 v_vinst\n\n')

            f.write('# restart 10000 restart1.lmp restart2.lmp\n\n')
            
            f.write('run 50000\n\n')

            f.write('variable lscale equal (f_VAVG/v_vinst)^(1.0/3.0)\n')
            f.write('print "scaling coordinates by ${lscale}"\n')
            f.write('change_box all x scale ${lscale} y scale ${lscale} '\
                    'z scale ${lscale} remap\n\n')

            f.write('unfix VAVG\n')
            f.write('unfix TPSTAT\n')
            f.write('fix TSTAT all nvt temp ${TK} ${TK} 100\n\n')

            f.write('run 10000\n\n')

            f.write('write_data data.eq.lmp\n')

        with open('data.lmp', 'w') as f:
            f.write('created by fftool\n\n')
            f.write('{:d} atoms\n'.format(natom))
            if nbond:
                f.write('{:d} bonds\n'.format(nbond))
            if nangle:
                f.write('{:d} angles\n'.format(nangle))
            if ndihed:
                f.write('{:d} dihedrals\n'.format(ndihed))
            # f.write('\n')
                
            f.write('{:d} atom types\n'.format(len(self.attype)))
            if nbond:
                f.write('{:d} bond types\n'.format(len(self.bdtype)))
            if nangle:
                f.write('{:d} angle types\n'.format(len(self.antype)))
            if ndihed:
                ndht = len(self.dhtype)     # needed later
                f.write('{:d} dihedral types\n'.format(ndht +
                                                        len(self.ditype)))

            if self.box.center:
                f.write('{:f} {:f} xlo xhi\n'.format(-self.box.lx / 2.0,
                                                      self.box.lx / 2.0))
                f.write('{:f} {:f} ylo yhi\n'.format(-self.box.ly / 2.0,
                                                      self.box.ly / 2.0))
                f.write('{:f} {:f} zlo zhi\n'.format(-self.box.lz / 2.0,
                                                      self.box.lz / 2.0))
            else:
                f.write('{:f} {:f} xlo xhi\n'.format(0.0, self.box.lx))
                f.write('{:f} {:f} ylo yhi\n'.format(0.0, self.box.ly))
                f.write('{:f} {:f} zlo zhi\n'.format(0.0, self.box.lz))
            if self.box.triclinic:
                f.write('{:f} {:f} {:f} xy xz yz\n'.format(
                    self.box.xy, self.box.xz, self.box.yz))

            f.write('\nMasses\n\n')
            for att in self.attype:
                f.write('{:4d} {:8.3f}  # {}\n'.format(
                    att.ityp + 1, att.m, att.name))

            if nbond:
                f.write('\nBond Coeffs\n\n')
                for bdt in self.bdtype:
                    f.write('{:4d} {:12.6f} {:12.6f}  # {}\n'.format(
                        bdt.ityp + 1, bdt.par[1] / (2.0 * ecnv),
                        bdt.par[0], bdt.name))

            if nangle:
                f.write('\nAngle Coeffs\n\n')
                for ant in self.antype:
                    f.write('{:4d} {:12.6f} {:12.6f}  # {}\n'.format(
                        ant.ityp + 1, ant.par[1] / (2.0 * ecnv),
                        ant.par[0], ant.name))

            if ndihed:
                f.write('\nDihedral Coeffs\n\n')
                for dht in self.dhtype:
                    f.write('{0:4d} {1:12.6f} {2:12.6f} {3:12.6f} {4:12.6f}'\
                             '  # {5}\n'.format(dht.ityp + 1,
                              dht.par[0] / ecnv, dht.par[1] / ecnv,
                              dht.par[2] / ecnv, dht.par[3] / ecnv, dht.name))
                for dit in self.ditype:
                    f.write('{0:4d} {1:12.6f} {2:12.6f} {3:12.6f} {4:12.6f}'\
                             '  # {5}\n'.format(ndht + dit.ityp + 1,
                              dit.par[0] / ecnv, dit.par[1] / ecnv,
                              dit.par[2] / ecnv, dit.par[3] / ecnv, dit.name))

            f.write('\nAtoms\n\n')
            i = nmol = 0
            for sp in self.spec:
                for im in range(sp.nmol):
                    for at in sp.atom:
                        f.write('{0:7d} {1:7d} {2:4d} {3:10.6f} '\
                                 '{4:13.6e} {5:13.6e} {6:13.6e}  # {7} {8}\n'\
                                 .format(i + 1, nmol + 1, at.ityp + 1, at.q, 
                                 self.x[i], self.y[i], self.z[i],
                                 at.name, sp.name))
                        i += 1
                    nmol += 1

            if nbond:
                f.write('\nBonds\n\n')
                i = shift = 1
                for sp in self.spec:
                    natom = len(sp.atom)
                    for im in range(sp.nmol):
                        for bd in sp.bond:
                            f.write('{0:7d} {1:4d} {2:7d} {3:7d}  # {4}\n'\
                                .format(i, bd.ityp + 1,
                                bd.i + shift, bd.j + shift, bd.name))
                            i += 1
                        shift += natom

            if nangle:
                f.write('\nAngles\n\n')
                i = shift = 1
                for sp in self.spec:
                    natom = len(sp.atom)
                    for im in range(sp.nmol):
                        for an in sp.angle:
                            f.write('{0:7d} {1:4d} {2:7d} {3:7d} {4:7d}  '\
                                     '# {5}\n'.format(i, an.ityp + 1,
                                     an.i + shift, an.j + shift, an.k + shift,
                                     an.name))
                            i += 1
                        shift += natom

            if ndihed:
                f.write('\nDihedrals\n\n')
                i = shift = 1
                for sp in self.spec:
                    natom = len(sp.atom)
                    for im in range(sp.nmol):
                        for dh in sp.dihed:
                            f.write('{0:7d} {1:4d} {2:7d} {3:7d} {4:7d} '\
                                     '{5:7d}  # {6}\n'.format(i, dh.ityp + 1,
                                     dh.i + shift, dh.j + shift, dh.k + shift,
                                     dh.l + shift, dh.name))
                            i += 1
                        for di in sp.dimpr:
                            f.write('{0:7d} {1:4d} {2:7d} {3:7d} {4:7d} '\
                                     '{5:7d}  # {6}\n'.format(i,
                                     ndht + di.ityp + 1, di.i + shift,
                                     di.j + shift, di.k + shift, di.l + shift,
                                     di.name))
                            i += 1
                        shift += natom
                    
            # f.write('\n')


    def writepdb(self):
        with open('config.pdb', 'w') as f:
            f.write('TITLE     created by fftool\n')
            f.write('REMARK    SIMBOX\n')
            f.write('CRYST1{0:9.3f}{1:9.3f}{2:9.3f}{3:7.2f}{4:7.2f}{5:7.2f} '\
                    '{6:11s}{7:4d}\n'.format(
                    self.box.a, self.box.b, self.box.c,
                    self.box.alpha, self.box.beta, self.box.gamma, 'P 1', 1))
            i = nmol = 0
            for sp in self.spec:
                for im in range(sp.nmol):
                    j = 1
                    for at in sp.atom:
                        if len(at.uname) > 4:
                            print('warning: atom name ' + at.uname +
                                ' too long for pdb in ' + sp.name)
                        f.write('HETATM{0:5d} {1:4s} {2:3s}  {3:4d}    '\
                                '{4:8.3f}{5:8.3f}{6:8.3f}  1.00  0.00'\
                                '          {7:>2s}\n'.format(i + 1,
                                at.uname[:4], sp.res, nmol + 1,
                                self.x[i], self.y[i], self.z[i],
                                atomic_symbol(at.name)))
                        j += 1
                        i += 1
                    nmol += 1

            i = shift = 1
            for sp in self.spec:
                natom = len(sp.atom)
                for im in range(sp.nmol):
                    for bd in sp.bond:
                        if bd.i < bd.j:
                            f.write('CONECT{0:5d}{1:5d}\n'.format(
                                bd.i + shift, bd.j + shift))
                        else:
                            f.write('CONECT{0:5d}{1:5d}\n'.format(
                                bd.j + shift, bd.i + shift))
                        i += 1
                    shift += natom

            f.write('END\n')


    def checkdupresidues(self):
        '''check if residue names are unique'''
        residues = []
        for sp in self.spec:
            if sp.res not in residues:
                residues.append(sp.res)
            else:
                raise RuntimeError('duplicate residues ' + sp.res)


    def writexml(self, mix='g', allpairs='False', types='False'):

        self.checkdupresidues()

        natom = nbond = nangle = ndihed = 0
        for sp in self.spec:
            natom += sp.nmol * len(sp.atom)
            nbond += sp.nmol * len(sp.bond)
            nangle += sp.nmol * len(sp.angle)
            ndihed += sp.nmol * (len(sp.dihed) + len(sp.dimpr))

        root = ET.Element('ForceField')
        comment = ET.Comment('created by fftool; mix = {}'.format(mix))
        root.append(comment)
        ftree = ET.ElementTree(root)
        root = ftree.getroot()

        atomtypes = ET.SubElement(root, 'AtomTypes')
        for sp in self.spec:
            for at in sp.atom:
                attype = ET.SubElement(atomtypes, 'Type')
                attype.set('name', at.utype)
                attype.set('class', at.type)
                attype.set('element', atomic_symbol(at.name))
                attype.set('mass', '{:.3f}'.format(at.m))

        residues = ET.SubElement(root, 'Residues')
        for sp in self.spec:
            residue = ET.SubElement(residues, 'Residue')
            residue.set('name', sp.name)
            for at in sp.atom:
                atom = ET.SubElement(residue, 'Atom')
                atom.set('name', at.uname)
                atom.set('type', at.utype)
                atom.set('charge', '{}'.format(at.q))
            for bd in sp.bond:
                bond = ET.SubElement(residue, 'Bond')
                bond.set('atomName1', sp.atom[bd.i].uname)
                bond.set('atomName2', sp.atom[bd.j].uname)

        if nbond:
            bondforce = ET.SubElement(root, 'HarmonicBondForce')
            for bdt in self.bdtype:
                bond = ET.SubElement(bondforce, 'Bond')
                bond.set('class1', bdt.iatp)
                bond.set('class2', bdt.jatp)
                bond.set('length', '{:.5f}'.format(bdt.par[0] / 10.0))
                bond.set('k', '{:.1f}'.format(bdt.par[1] * 100.0))
    
        if nangle:
            angleforce = ET.SubElement(root, 'HarmonicAngleForce')
            for ant in self.antype:
                bond = ET.SubElement(angleforce, 'Angle')
                bond.set('class1', ant.iatp)
                bond.set('class2', ant.jatp)
                bond.set('class3', ant.katp)
                bond.set('angle', '{:.5f}'.format(ant.par[0] * math.pi/180.0))
                bond.set('k', '{:.2f}'.format(ant.par[1]))

        if ndihed:
            torsionforce = ET.SubElement(root, 'RBTorsionForce')
            eps = 1e-12
            for dht in self.dhtype:
                # convert OPLS to RB
                c0 = dht.par[1] + 0.5 * (dht.par[0] + dht.par[2]) + eps
                c1 = 0.5 * (-dht.par[0] + 3 * dht.par[2]) + eps
                c2 = -dht.par[1] + 4 * dht.par[3] + eps
                c3 = -2 * dht.par[2] + eps
                c4 = -4 * dht.par[3] + eps
                c5 = 0.0
                dihed = ET.SubElement(torsionforce, 'Proper')
                dihed.set('class1', dht.iatp)
                dihed.set('class2', dht.jatp)
                dihed.set('class3', dht.katp)
                dihed.set('class4', dht.latp)
                dihed.set('c0', '{:.5f}'.format(c0))
                dihed.set('c1', '{:.5f}'.format(c1))
                dihed.set('c2', '{:.5f}'.format(c2))
                dihed.set('c3', '{:.5f}'.format(c3))
                dihed.set('c4', '{:.5f}'.format(c4))
                dihed.set('c5', '{:.5f}'.format(c5))

            for dit in self.ditype:
                # convert OPLS to RB
                c0 = dit.par[1] + 0.5 * (dit.par[0] + dit.par[2]) + eps
                c1 = 0.5 * (-dit.par[0] + 3 * dit.par[2]) + eps
                c2 = -dit.par[1] + 4 * dit.par[3] + eps
                c3 = -2 * dit.par[2] + eps
                c4 = -4 * dit.par[3] + eps
                c5 = 0.0
                dimpr = ET.SubElement(torsionforce, 'Improper')
                dimpr.set('class1', dit.iatp)
                dimpr.set('class2', dit.jatp)
                dimpr.set('class3', dit.katp)
                dimpr.set('class4', dit.latp)
                dimpr.set('c0', '{:.5f}'.format(c0))
                dimpr.set('c1', '{:.5f}'.format(c1))
                dimpr.set('c2', '{:.5f}'.format(c2))
                dimpr.set('c3', '{:.5f}'.format(c3))
                dimpr.set('c4', '{:.5f}'.format(c4))
                dimpr.set('c5', '{:.5f}'.format(c5))

        if allpairs or mix == 'g':
            nbforce = ET.SubElement(root, 'NonbondedForce')
            nbforce.set('coulomb14scale', '0.5')
            nbforce.set('lj14scale', '0.5')
            resattr = ET.SubElement(nbforce, 'UseAttributeFromResidue')
            resattr.set('name', 'charge')
            if types:
                for sp in self.spec:
                    for at in sp.atom:
                        atom = ET.SubElement(nbforce, 'Atom')
                        atom.set('type', at.utype)
                        atom.set('sigma', '1.0')
                        atom.set('epsilon', '0.0')
            else:
                for att in self.attype:
                    atom = ET.SubElement(nbforce, 'Atom')
                    atom.set('class', att.type)
                    atom.set('sigma', '1.0')
                    atom.set('epsilon', '0.0')

            ljforce = ET.SubElement(root, 'LennardJonesForce')
            ljforce.set('lj14scale', '0.5')
            if types:
                for sp in self.spec:
                    for at in sp.atom:
                        atom = ET.SubElement(ljforce, 'Atom')
                        atom.set('type', at.utype)
                        atom.set('sigma', '{:.4f}'.format(at.par[0] / 10.0))
                        atom.set('epsilon', '{:.5f}'.format(at.par[1]))
                pairs = []
                for spi in self.spec:
                    for ati in spi.atom:
                        for spj in self.spec:
                            for atj in spj.atom:
                                if ati.utype == atj.utype:
                                    continue
                                ij = ati.utype + '-' + atj.utype
                                ji = atj.utype + '-' + ati.utype
                                if ij not in pairs and ji not in pairs:
                                    pairs.append(ij)
                                else:
                                    continue
                                for nb in self.vdw:
                                    if nb.iatp == ati.type and nb.jatp == atj.type or\
                                    nb.jatp == ati.type and nb.iatp == atj.type:
                                        break
                                nbfix = ET.SubElement(ljforce, 'NBFixPair')
                                nbfix.set('type1', ati.utype)
                                nbfix.set('type2', atj.utype)
                                nbfix.set('sigma', '{:.8f}'.format(
                                    nb.par[0] / 10.0))
                                nbfix.set('epsilon', '{:.8f}'.format(
                                    nb.par[1]))

            else:
                for att in self.attype:
                    atom = ET.SubElement(ljforce, 'Atom')
                    atom.set('class', att.type)
                    atom.set('sigma', '{:.4f}'.format(att.par[0] / 10.0))
                    atom.set('epsilon', '{:.5f}'.format(att.par[1]))
                pairs = []
                for nb in self.vdw:
                    if nb.iatp == nb.jatp:
                        continue
                    ij = nb.iatp + '-' + nb.jatp
                    ji = nb.jatp + '-' + nb.iatp
                    if ij not in pairs and ji not in pairs:
                        pairs.append(ij)
                        nbfix = ET.SubElement(ljforce, 'NBFixPair')
                        nbfix.set('class1', nb.iatp)
                        nbfix.set('class2', nb.jatp)
                        nbfix.set('sigma', '{:.8f}'.format(nb.par[0] / 10.0))
                        nbfix.set('epsilon', '{:.8f}'.format(nb.par[1]))

        else:
            nbforce = ET.SubElement(root, 'NonbondedForce')
            nbforce.set('coulomb14scale', '0.5')
            nbforce.set('lj14scale', '0.5')
            resattr = ET.SubElement(nbforce, 'UseAttributeFromResidue')
            resattr.set('name', 'charge')
            if types:
                for sp in self.spec:
                    for at in sp.atom:
                        atom = ET.SubElement(nbforce, 'Atom')
                        atom.set('type', at.utype)
                        atom.set('sigma', '{:.4f}'.format(at.par[0] / 10.0))
                        atom.set('epsilon', '{:.5f}'.format(at.par[1]))
            else:
                for att in self.attype:
                    atom = ET.SubElement(nbforce, 'Atom')
                    atom.set('class', att.type)
                    atom.set('sigma', '{:.4f}'.format(att.par[0] / 10.0))
                    atom.set('epsilon', '{:.5f}'.format(att.par[1]))

        indent_xml(root)
        ftree.write('field.xml')

        self.writepdb()


    def writecharmm(self, mix='g', allpairs=False):

        self.checkdupresidues()

        with open('field.str', 'w') as f:
            f.write('* created by fftool; mix = {}\n\n'.format(mix))

            f.write('read rtf card append\n\n')

            for sp in self.spec:
                f.write('RESI {} {:7.3f}\n'.format(sp.name, sp.charge()))
                f.write('GROUP\n')
                for at in sp.atom:
                    f.write('ATOM {:5s} {:5s} {:7.3f}\n'.format(
                        at.uname, at.name, at.q))
                for bd in sp.bond:
                    f.write('BOND {:5s} {:5s}\n'.format(
                        sp.atom[bd.i].uname, sp.atom[bd.j].uname))
                f.write('\n')
            f.write('END\n\n')

            f.write('read para card flex append\n\n')

            f.write('ATOMS\n')
            types = []
            for att in self.attype:
                if att.type not in types:
                    types.append(att.type)
                    f.write('MASS  -1  {:5s} {:9.5f}\n'.format(
                        att.type, att.m))
            f.write('\n')

            if mix == 'g':  # most likely geom is ignored
                f.write('NONBONDED nbxmod 5 e14fac 0.5 geom\n')
            else:
                f.write('NONBONDED nbxmod 5 e14fac 0.5\n')

            f.write('!atom  ignored  epsilon   Rmin/2   ignored  eps,1-4   '\
                    'Rmin/2,1-4\n')
            types = []
            for att in self.attype:
                if att.type not in types:
                    types.append(att.type)
                    rmin_2 = (att.par[0] / 2.0) * 2.0**(1.0/6.0) 
                    f.write('{:5s}  0.0    {:9.5f} {:9.5f}  0.0    '\
                            '{:9.5f} {:9.5f}\n'.format(att.type,
                            -att.par[1] / kCal, rmin_2,
                            -att.par[1] / (2 * kCal), rmin_2))
            f.write('\n')

            if allpairs or mix == 'g':
                f.write('NBFIX\n')
                f.write('!ai   aj      epsilon   Rmin      eps,1-4   Rmin,1-4\n')
                pairs = []
                for nb in self.vdw:
                    ij = nb.iatp + '-' + nb.jatp
                    ji = nb.jatp + '-' + nb.iatp
                    if ij not in pairs and ji not in pairs:
                        pairs.append(ij)
                        rmin = nb.par[0] * 2.0**(1.0/6.0)
                        f.write('{:5s} {:5s} {:9.5f} {:9.5f} {:9.5f} '\
                            '{:9.5f}\n'.format(nb.iatp, nb.jatp,
                            -nb.par[1] / kCal, rmin,
                            -nb.par[1] / (2 * kCal), rmin))
                f.write('\n')

            f.write('BONDS\n')
            f.write('!ai   aj      kb        b0\n')
            for bdt in self.bdtype:
                f.write('{:5s} {:5s} {:8.2f} {:8.3f}\n'.format(
                    bdt.iatp, bdt.jatp, bdt.par[1] / (2 * kCal), bdt.par[0]))
            f.write('\n')

            f.write('ANGLES\n')
            f.write('!ai   aj    ak      kth     th0\n')
            for ant in self.antype:
                f.write('{:5s} {:5s} {:5s} {:7.2f} {:8.2f}\n'.format(
                    ant.iatp, ant.jatp, ant.katp,
                    ant.par[1] / (2 * kCal), ant.par[0]))
            f.write('\n')

            f.write('DIHEDRALS\n')
            f.write('!ai   aj    ak    al      kchi   n   delta\n')
            for dht in self.dhtype:
                zero = True
                for i in range(4):
                    if dht.par[i] != 0.0:
                        zero = False
                        kchi = dht.par[i] / (2.0 * kCal)
                        delta = (i % 2) * 180.0  # 180 on V2 (i=1) and V4 (i=3)
                        f.write('{:5s} {:5s} {:5s} {:5s} {:7.3f}  {:1d}'\
                            ' {:8.2f}\n'.format(dht.iatp, dht.jatp, dht.katp,
                            dht.latp, kchi, i + 1, delta))
                if zero:
                     f.write('{:5s} {:5s} {:5s} {:5s} {:7.3f}  {:1d}'\
                        ' {:8.2f}\n'.format(dht.iatp, dht.jatp, dht.katp,
                        dht.latp, 0.0, 1, 0.0))

            f.write('\n')

            f.write('IMPROPER\n')
            f.write('!ai   aj    ak    al      kchi   n   delta\n')
            for dit in self.ditype:
                zero = True
                for i in range(4):
                    if dit.par[i] != 0.0:
                        zero = False
                        kchi = dit.par[i] / (2.0 * kCal)
                        delta = (i % 2) * 180.0
                        f.write('{:5s} {:5s} {:5s} {:5s} {:7.3f}  {:1d}'\
                            ' {:8.2f}\n'.format(dit.iatp, dit.jatp, dit.katp,
                            dit.latp, kchi, i + 1, delta))                    
                if zero:
                     f.write('{:5s} {:5s} {:5s} {:5s} {:7.3f}  {:1d}'\
                        ' {:8.2f}\n'.format(dht.iatp, dht.jatp, dht.katp,
                        dht.latp, 0.0, 1, 0.0))
            f.write('\n')
            f.write('END\n')

        self.writepsf()
        self.writepdb()


    def writegmx(self, mix='g'):

        self.checkdupresidues()

        with open('field.top', 'w') as f:
            f.write('! created by fftool; mix = {}\n\n'.format(mix))
            
            f.write('[ defaults ]\n')
            if mix == 'g':
                combrule = 3
            else:
                combrule = 2
            f.write('; nbfunc   comb-rule   gen-pairs   fudgeLJ fudgeQQ\n')
            f.write('  1        {:1d}           yes         0.5     0.5\n\n'\
                    .format(combrule))
            
            f.write('[ atomtypes ]\n')
            f.write('; name  at.nr     mass   charge  ptype  '\
                    'sigma        epsilon\n')
            for att in self.attype:
                f.write('{:4s}       {:2d} {:8.4f} {:8.4f}      A '\
                        '{:12.5e} {:12.5e}\n'.format(att.name,
                        atomic_number(att.name),
                        att.m, att.q, att.par[0]/10., att.par[1]))
            f.write('\n')

            for sp in self.spec:
                f.write('[ moleculetype ]\n')
                f.write('; name       nrexcl\n')
                f.write('{:16s}  {:1d}\n\n'.format(sp.name, 3))

                f.write('[ atoms ]\n')
                f.write(';  nr   type  resnr  residu  atom   cgnr    charge\n')
                i = 1
                for at in sp.atom:
                    f.write('{:5d}   {:4s}  {:5d}  {:5s}   {:5s}  {:4d}'\
                            '  {:10.6f}\n'.format(i, at.name, 1,
                            sp.res, at.uname, i, at.q))
                    i += 1
                f.write('\n')

                f.write('[ bonds ]\n')
                f.write(';  ai    aj   func    b0        kb\n')
                for bd in sp.bond:
                    if bd.pot != 'cons':
                        f.write('{:5d} {:5d}     {:2d}  {:9.5f}  {:9.1f}\n'\
                                .format(bd.i + 1, bd.j + 1, 1,
                                bd.par[0]/10.0, bd.par[1]*100.0))
                f.write('\n')

                f.write('[ constraints ]\n')
                f.write(';  ai    aj   func    b0\n')
                for bd in sp.bond:
                    if bd.pot == 'cons':
                        f.write('{:5d} {:5d}     {:2d}  {:9.5f}\n'\
                                .format(bd.i + 1, bd.j + 1, 1, bd.par[0]/10.0))
                f.write('\n')

                # 1-4 exclusion list built from bonds instead of dihedrals
                pairs12_set = set()
                pairs13_set = set()
                pairs14_set = set()
                for bd in sp.bond:
                    a2, a3 = bd.i, bd.j
                    pairs12_set.add(tuple(sorted([a2, a3])))
                    for a1 in sp.atom[a2].bond_partners:
                        if a1 != a3:
                            pairs13_set.add(tuple(sorted([a1, a3])))
                    for a4 in sp.atom[a3].bond_partners:
                        if a2 != a4:
                            pairs13_set.add(tuple(sorted([a2, a4])))
                    for a1 in sp.atom[a2].bond_partners:
                        for a4 in sp.atom[a3].bond_partners:
                            if a1 != a3 and a2 != a4 and a1 != a4:
                                pairs14_set.add(tuple(sorted([a1, a4])))
                # remove 1-2 and 1-3 pairs if there are 4- or 5-member rings
                pairs14 = tuple(sorted(pairs14_set -
                                           pairs12_set.union(pairs13_set)))

                f.write('[ pairs ]\n')
                f.write(';   ai   aj   func\n')
                for i, j in pairs14:
                    f.write('{:5d} {:5d}     {:2d}\n'.format(i + 1, j + 1, 1))
                f.write('\n')

                f.write('[ angles ]\n')
                f.write(';  ai    aj    ak   func    th0        cth\n')
                for an in sp.angle:
                    f.write('{:5d} {:5d} {:5d}     {:2d}  {:9.3f}  {:9.3f}\n'\
                             .format(an.i + 1, an.j + 1, an.k + 1, 1,
                             an.par[0], an.par[1]))
                f.write('\n')

                f.write('[ dihedrals ]\n')
                f.write(';  ai    aj    ak    al   func    coefficients\n')
                for dh in sp.dihed:
                    f.write('{0:5d} {1:5d} {2:5d} {3:5d}     {4:2d}  '
                            '{5:9.5f} {6:9.5f} {7:9.5f} {8:9.5f}\n'\
                             .format(dh.i + 1, dh.j + 1, dh.k + 1, dh.l + 1, 5,
                             dh.par[0], dh.par[1], dh.par[2], dh.par[3]))
                for di in sp.dimpr:
                    f.write('{0:5d} {1:5d} {2:5d} {3:5d}     {4:2d}  '
                            '{5:9.5f} {6:9.5f} {7:9.5f} {8:9.5f}\n'\
                             .format(di.i + 1, di.j + 1, di.k + 1, di.l + 1, 5,
                             di.par[0], di.par[1], di.par[2], di.par[3]))
                f.write('\n')

            f.write('[ system ]\n')
            f.write('simbox\n\n')

            f.write('[ molecules ]\n')
            for sp in self.spec:
                f.write('{:16s} {:5d}\n'.format(sp.name, sp.nmol))

        self.writepdb()

        with open('run.mdp', 'w') as f:
            f.write('integrator            = sd; md\n')
            f.write('dt                    = 0.001\n')
            f.write('nsteps                = 10000\n\n')
            
            f.write('nstlog                = 1000\n')
            f.write('nstxout-compressed    = 1000\n\n')

            f.write('cutoff-scheme         = Verlet\n')
            f.write('rlist                 = 1.2\n')
            f.write('pbc                   = xyz\n\n')

            f.write('coulombtype           = PME\n')
            f.write('rcoulomb              = 1.2\n')
            f.write('ewald-rtol            = 1.0e-5\n')
            f.write('vdwtype               = Cut-off\n')
            f.write('rvdw                  = 1.2\n')
            f.write('DispCorr              = EnerPres\n\n')

            f.write('tcoupl                = no; V-rescale\n')
            f.write('tc-grps               = System\n')
            f.write('tau-t                 = 1.0; 0.1\n')
            f.write('ref-t                 = 300.0\n\n')

            f.write('pcoupl                = Berendsen; Parrinello-Rahman\n')
            f.write('pcoupltype            = isotropic\n')
            f.write('tau-p                 = 0.5; 5.0\n')
            f.write('ref-p                 = 1.0\n')
            f.write('compressibility       = 4.5e-5\n')

            f.write('gen-vel               = yes\n')
            f.write('gen-temp              = 300\n')
            f.write('gen-seed              = -1\n\n')

            f.write('constraints           = h-bonds\n')
            f.write('constraint-algorithm  = LINCS\n')
            f.write('continuation          = no\n\n')
            
    def writedlp(self, cos4=False):
        with open('FIELD', 'w') as f:
            f.write('created by fftool\n')
            f.write('units kJ\n\n')
            
            f.write('molecular types {:d}\n'.format(len(self.spec)))
            for sp in self.spec:
                f.write('{0}\n'.format(sp.name))
                f.write('nummols {:d}\n'.format(sp.nmol))
                f.write('atoms {:d}\n'.format(len(sp.atom)))
                for at in sp.atom:
                    f.write('{:5s} {:8.4f} {:6.3f} 1  # {}\n'.format(
                            at.name, at.m, at.q, at.type))
                ncons = 0
                for bd in sp.bond: 
                    if bd.pot == 'cons':
                        ncons += 1
                f.write('constraints {:d}\n'.format(ncons))
                for bd in sp.bond:
                    if bd.pot == 'cons':
                        f.write('{:4d} {:4d} {:6.3f}  # {}\n'.format(
                                bd.i + 1, bd.j + 1, bd.par[0], bd.name))
                f.write('bonds {:d}\n'.format(len(sp.bond) - ncons))
                for bd in sp.bond:
                    if bd.pot != 'cons':
                        f.write('{0:4s} {1:4d} {2:4d} {3:7.1f} {4:6.3f}  '
                                '# {5}\n'.format(bd.pot, bd.i + 1, bd.j + 1,
                                 bd.par[1], bd.par[0], bd.name))
                f.write('angles {:d}\n'.format(len(sp.angle)))
                for an in sp.angle:
                    f.write('{0:4s} {1:4d} {2:4d} {3:4d} {4:7.2f} {5:7.2f}  '
                            '# {6}\n'.format(an.pot, an.i + 1, an.j + 1,
                            an.k + 1, an.par[1], an.par[0], an.name))
                f.write('dihedrals {:d}\n'.format(len(sp.dihed) +
                                                   len(sp.dimpr)))
                for dh in sp.dihed:
                    if cos4:
                        pot = 'cos4'
                        f.write('{0:4s} {1:4d} {2:4d} {3:4d} {4:4d} '
                                '{5:9.4f} {6:9.4f} {7:9.4f} {8:9.4f} '
                                '{9:6.3f} {10:6.3f}  # {11}\n'.format(pot,
                                 dh.i + 1, dh.j + 1, dh.k + 1, dh.l + 1,
                                 dh.par[0], dh.par[1], dh.par[2], dh.par[3],
                                 0.5, 0.5, dh.name))
                    else:
                        pot = 'cos3'
                        f.write('{0:4s} {1:4d} {2:4d} {3:4d} {4:4d} '
                                '{5:9.4f} {6:9.4f} {7:9.4f} '
                                '{8:6.3f} {9:6.3f}  # {10}\n'.format(pot,
                                dh.i + 1, dh.j + 1, dh.k + 1, dh.l + 1,
                                dh.par[0], dh.par[1], dh.par[2],
                                0.5, 0.5, dh.name))
                for di in sp.dimpr:
                    if cos4:
                        pot = 'cos4'
                        f.write('{0:4s} {1:4d} {2:4d} {3:4d} {4:4d} '
                                '{5:9.4f} {6:9.4f} {7:9.4f} {8:9.4f} '
                                '{9:6.3f} {10:6.3f}  # {11}\n'.format(pot,
                                di.i + 1, di.j + 1, di.k + 1, di.l + 1,
                                di.par[0], di.par[1], di.par[2], di.par[3],
                                0.5, 0.5, di.name))
                    else:
                        pot = 'cos3'
                        f.write('{0:4s} {1:4d} {2:4d} {3:4d} {4:4d} '
                                '{5:9.4f} {6:9.4f} {7:9.4f} '
                                '{8:6.3f} {9:6.3f}  # {10}\n'.format(pot,
                                di.i + 1, di.j + 1, di.k + 1, di.l + 1,
                                di.par[0], di.par[1], di.par[2],
                                0.5, 0.5, di.name))
                f.write('finish\n')

            f.write('vdw {:d}\n'.format(len(self.vdw)))
            for nb in self.vdw:
                if nb.pot == 'lj':
                    f.write('{0:5s} {1:5s} {2:>4s} {3:10.6f} '
                            '{4:8.4f}\n'.format(nb.i, nb.j, nb.pot,
                            nb.par[1], nb.par[0]))
            f.write('close\n')

        with open('CONFIG', 'w') as f:
            f.write('created by fftool\n')
            if self.box.triclinic:
                imcon = 3
            elif self.box.a == self.box.b and self.box.b == self.box.c:
                imcon = 1
            else:
                imcon = 2
            f.write(' {:9d} {:9d} {:9d}\n'.format(0, imcon, self.natom))
            f.write(' {:19.9f} {:19.9f} {:19.9f}\n'.format(self.box.lx,
                    0.0, 0.0))
            f.write(' {:19.9f} {:19.9f} {:19.9f}\n'.format(self.box.xy,
                    self.box.ly, 0.0))
            f.write(' {:19.9f} {:19.9f} {:19.9f}\n'.format(self.box.xz,
                    self.box.yz, self.box.lz))

            i = 0
            for sp in self.spec:
                for im in range(sp.nmol):
                    for at in sp.atom:
                        f.write('{:8s} {:9d}\n'.format(at.name, i + 1))
                        f.write(' {:19.9f} {:19.9f} {:19.9f}\n'\
                            .format(self.x[i], self.y[i], self.z[i]))
                        i += 1

    def writepsf(self):
        natom = nbond = nangle = ndihed = ndimpr = 0
        for sp in self.spec:
            natom += sp.nmol * len(sp.atom)
            nbond += sp.nmol * len(sp.bond)
            nangle += sp.nmol * len(sp.angle)
            ndihed += sp.nmol * len(sp.dihed)
            ndimpr += sp.nmol * len(sp.dimpr)

        with open('data.psf', 'w') as f:
            f.write('PSF\n\n')
            f.write('       1 !NTITLE\n')
            f.write(' REMARKS Created by fftool\n')

            f.write('\n{:8d} !NATOM\n'.format(natom))
            i = nmol = 0
            for sp in self.spec:
                for im in range(sp.nmol):
                    for at in sp.atom:
                        f.write('{0:8d} S    {1:<4d} {2:>8s} {3:4s} {4:4s} '
                                '{5:10.6f} {6:13.4f} {7:11d}\n'.format(
                                i + 1, nmol + 1, sp.name[:8], at.uname, at.type,
                                at.q, at.m, 0))
                        i += 1
                    nmol += 1

            f.write('\n{:8d} !NBOND: bonds\n'.format(nbond))
            i = shift = 1
            for sp in self.spec:
                natom = len(sp.atom)
                for im in range(sp.nmol):
                    for bd in sp.bond:
                        f.write(' {:7d} {:7d}'.format(bd.j + shift,
                                                      bd.i + shift))
                        if (i % 4) == 0:
                            f.write('\n')
                        i += 1
                    shift += natom
            if ((i - 1) % 4) != 0:
                f.write('\n')

            f.write('\n{:8d} !NTHETA: angles\n'.format(nangle))
            i = shift = 1
            for sp in self.spec:
                natom = len(sp.atom)
                for im in range(sp.nmol):
                    for an in sp.angle:
                        f.write(' {:7d} {:7d} {:7d}'.format(an.i + shift,
                                an.j + shift, an.k + shift))
                        if (i % 3) == 0:
                            f.write('\n')
                        i += 1
                    shift += natom
            if ((i - 1) % 3) != 0:
                f.write('\n')

            f.write('\n{:8d} !NPHI: dihedrals\n'.format(ndihed))
            i = shift = 1
            for sp in self.spec:
                natom = len(sp.atom)
                for im in range(sp.nmol):
                    for dh in sp.dihed:
                        f.write(' {:7d} {:7d} {:7d} {:7d}'.format(
                                dh.i + shift, dh.j + shift, dh.k + shift,
                                dh.l + shift))
                        if (i % 2) == 0:
                            f.write('\n')
                        i += 1
                    shift += natom
            if ((i - 1) % 2) != 0:
                f.write('\n')

            f.write('\n{:8d} !NIMPHI: impropers\n'.format(ndimpr))
            i = shift = 1
            for sp in self.spec:                     
                natom = len(sp.atom)
                for im in range(sp.nmol):
                    for di in sp.dimpr:
                        f.write(' {:7d} {:7d} {:7d} {:7d}'.format(
                                di.i + shift, di.j + shift, di.k + shift,
                                di.l + shift))
                        if (i % 2) == 0:
                            f.write('\n')
                        i += 1
                    shift += natom
            if ((i - 1) % 2) != 0:
                f.write('\n')

            f.write('\n')
                    
# --------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description = 'Generate files with force-field and atomic '\
        'coordinates for molecular dynamics, from molecule description files '\
        'in z-matrix, MDL mol, PDB or xyz formats, and a force field file. '\
        'Creates a pack.inp file for Packmol to place molecules in the '\
        'simulation box. Then rerun selecting an option to create input '\
        'files for different MD codes. '\
        'The name of a file with force field parameters can be supplied: '\
        'i) on a line at the end of the .zmat file, '\
        'ii) on the 3rd line of the .mol file, or on the 1st after the '\
        'molecule name, '\
        'iii) after the molecule name in a COMPND record in the .pdb file, '\
        'iv) on the 2nd line of the .xyz file after the molecule name.')
    parser.add_argument('-b', '--box', default = '', help = 'box length in A '\
                        '(cubic), for non-cubic boxes supply '
                        'a,b,c[,alpha,beta,gamma] default box '\
                        'is orthogonal (alpha = beta = gamma = 90.0)')
    parser.add_argument('-r', '--rho', type=float, default = 0.0,
                        help = 'density in mol/L')
    parser.add_argument('-c', '--center', action = 'store_true',
                        help = 'center box on origin')
    parser.add_argument('-t', '--tol', type=float, default = 2.5,
                        help = 'tolerance for Packmol (default: 2.5)')
    parser.add_argument('-m', '--mix', default = 'g',
                        help = '[a]rithmetic or [g]eometric sigma_ij '\
                        '(default: g)')
    parser.add_argument('-l', '--lammps', action = 'store_true', 
                        help = 'create LAMMPS files in.lmp data.lmp '\
                        '(needs simbox.xyz created by Packmol)')
    parser.add_argument('-a', '--allpairs', action = 'store_true', 
                        help = 'write all I-J pairs to LAMMPS files')
    parser.add_argument('-u', '--units', default = 'r',
                        help = 'LAMMPS units [r]eal or [m]etal (default: r)')
    parser.add_argument('-p', '--pbc', default = '',
                        help = 'connect bonds across periodic boundaries in '\
                        'x, xy, xyz, etc. (default: none)')
    parser.add_argument('-x', '--xml', action = 'store_true',
                        help = 'create OpenMM files .xml .pdb '\
                        '(needs simbox.xyz created by Packmol)')
    parser.add_argument('--types', action='store_true',
                        help='unique atom types for non-bonded pairs in xml')
    parser.add_argument('--charmm', action = 'store_true',
                        help = 'create CHARMM files .str .psf .pdb '\
                        '(needs simbox.xyz created by Packmol)')
    parser.add_argument('-g', '--gmx', action = 'store_true',
                        help = 'create GROMACS files .top .gro .pdb '\
                        '(needs simbox.xyz created by Packmol)')
    parser.add_argument('-d', '--dlpoly', action = 'store_true',
                        help = 'create DLPOLY files FIELD CONFIG '\
                        '(needs simbox.xyz created by Packmol)')
    parser.add_argument('--cos4', action = 'store_true', 
                        help = 'use cos4 dihedrals in DLPOLY FIELD')
    parser.add_argument('infiles', nargs='+',
                        help = 'n1 infile1 [n2 infile2 ...], '\
                        'where n_i are the numbers of molecules defined in '\
                        'infile_i. Use extension .zmat, .mol, .pdb or .xyz')
    args = parser.parse_args()

    if len(args.infiles) == 1:
        nmols = [1]
        files = args.infiles
    else:
        nmols = args.infiles[::2]   # even elements are numbers of molecules
        files = args.infiles[1::2]  # odd elements are molecule files
    nmol = sum(int(n) for n in nmols)

    if args.box and args.rho != 0.0:
        raise RuntimeError('supply density or box dimensions, not both')
    
    if args.box:
        tok = args.box.split(',')
        if len(tok) == 1:
            a = b = c = float(tok[0])
            alpha = beta = gamma = 90.0
        elif len(tok) == 3:
            a, b, c = [ float(t) for t in tok ]
            alpha = beta = gamma = 90.0
        elif len(tok) == 6:
            a = float(tok[0])
            b = float(tok[1])
            c = float(tok[2])
            alpha = float(tok[3])
            beta = float(tok[4])
            gamma = float(tok[5])
        else:
            raise ValueError('wrong box dimensions and angles')
    elif args.rho != 0.0:
        a = b = c = math.pow(nmol / (args.rho * 6.022e+23 * 1.0e-27), 1./3.)
        alpha = beta = gamma = 90.0
    else:
        raise RuntimeError('density or box dimensions need to be supplied')

    box = cell(a, b, c, alpha, beta, gamma, args.pbc, args.center)
    rho = nmol / (box.vol * 1.0e-27 * 6.022e+23)
    print('density {:.3f} mol/L  volume {:.1f} A^3'.format(rho, box.vol))

    print('molecule_file      species           nmol force_field      '\
          'nbond source  charge')
    connect = True
    spec = []
    i = 0
    for zfile in files:
        spec.append(mol(zfile, connect, box))
        spec[i].nmol = int(nmols[i])
        spec[i].writexyz()
        print('  {:16s} {:16s} {:5d} {:16s} {:5d} {:5s} {:+8.4f}'\
            .format(zfile, spec[i].name, spec[i].nmol, spec[i].ffile,
                    spec[i].nbond, spec[i].topol, spec[i].charge()))
        i += 1

    sim = system(spec, box, args.mix)

    if args.lammps:
        sim.readcoords('simbox.xyz')
        if args.units == 'r':
            print('lammps files units real')
        elif args.units == 'm':
            print('lammps files units metal')
        else:
            raise ValueError('invalid units: choose [r]eal or [m]etal')
        print('  in.lmp\n  data.lmp')
        if (args.allpairs and len(sim.vdw) > 12):
            print('  pair.lmp')
        sim.writelmp(args.mix, args.allpairs, args.units)
    if args.xml:
        sim.readcoords('simbox.xyz')
        print('xml files\n  field.xml\n  config.pdb')
        sim.writexml(args.mix, args.allpairs, args.types)
    if args.charmm:
        sim.readcoords('simbox.xyz')
        print('charmm files\n  field.str\n  data.psf\n  config.pdb')
        sim.writecharmm(args.mix, args.allpairs)
    if args.gmx:
        sim.readcoords('simbox.xyz')
        print('gromacs files\n  run.mdp\n  field.top\n  config.pdb')
        sim.writegmx(args.mix)
    if args.dlpoly:
        sim.readcoords('simbox.xyz')
        print('dlpoly files\n  FIELD\n  CONFIG')
        sim.writedlp(args.cos4)
    if not (args.lammps or args.xml or args.charmm or args.gmx or args.dlpoly):
        print('packmol file\n  pack.inp')
        if args.pbc:
            boxtol = 0.0
        else:
            boxtol = 1.5
        sim.writepackmol('pack.inp', 'simbox.xyz', args.tol, boxtol)


if __name__ == '__main__':
    main()
