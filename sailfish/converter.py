# coding=utf-8
"""Converter between LB and physical coordinate systems."""
from __future__ import division

__author__ = 'Michal Januszewski'
__email__ = 'sailfish-cfd@googlegroups.com'
__license__ = 'LGPL3'

import math


class CoordinateConverter(object):
    """Converts between physical coordinates and LB coordinates.

    The physical <-> LB correspondece is established by a configuration
    dictionary. The following keys are currently recognized:

      axes: A permutation of the 'xyz' string. 'xyz' means that the
        original axes are not shuffled. Note that the physical memory
        layout of the LB simulation is the inverse of this layout.
      bounding_box: Span of the simulation domain in physical space as:
        [(x0, x1), (y0, y1), (z0, z1)].
      size: Size of the LB simulation domain.
      padding: Number of LB nodes that were added to the domain after
        conversion from the physical space, as:
        [fwd_x, back_x, fwd_y, back_y, fwd_z, back_z]
      cuts: Number of LB ndoes that were removed from the domain after
        conversion from the physical space, as:
        [(fwd_x, back_x), (fwd_y, back_y), (fwd_z, back_z)]
    """

    def __init__(self, config):
        """Initializes the converter.

        :param config: dictionary of settings from the .config file
        """
        ax = config['axes']
        self.axes = [ax.index('x'), ax.index('y'), ax.index('z')]

        # These fields are stored in the natural order (x, y, z) of the
        # underlying geometry.
        self.dx = []
        self.offset = []
        self.phys_min_x = []

        for i, phys_size in enumerate(config['bounding_box']):
            offset = -config['padding'][2 * i]

            # Convert the natural index to physical LB order.
            lb_i = 2 - i
            size = config['size'][lb_i]
            size -= config['padding'][2 * i]
            size -= config['padding'][2 * i + 1]

            # Physical size BEFORE cutting nodes from the envelope and before
            # any padding was added.
            phys_size = config['bounding_box'][i]

            # Lattice size BEFORE cutting nodes, after padding was removed.
            if 'cuts' in config:
                size += config['cuts'][i][0] + config['cuts'][i][1]
                offset += config['cuts'][i][0]

            self.offset.append(offset)

            # At this point 'size' corresponds to the size of the unprocessed LB
            # geometry, as generated by the voxelizer, but without padding.
            dx = (phys_size[1] - phys_size[0]) / size
            self.dx.append(dx)
            self.phys_min_x.append(phys_size[0])

    # Physical coordinates are always given in natural order (x, y, z).
    # The return value is in physical LB order.
    def to_lb(self, phys_pos, round_=True):
        lb_pos = [0, 0, 0]
        for i, phys_x in enumerate(phys_pos):
            lb_pos[2 - self.axes[i]] = ((phys_x - self.phys_min_x[i]) /
                                        self.dx[i] - self.offset[i])

        if round_:
            lb_pos = [int(round(x)) for x in lb_pos]
        return lb_pos

    # lb_pos is in physical LB order.
    # The return value is in natural order (x, y, z) for the underlying
    # geometry.
    def from_lb(self, lb_pos):
        phys_pos = [0, 0, 0]
        for i, lb_x in enumerate(lb_pos):
            i = self.axes.index(2 - i)
            phys_pos[i] = (self.dx[i] * (lb_x + self.offset[i]) + self.phys_min_x[i])
        return phys_pos


class UnitConverter(object):
    """Performs unit conversions."""

    def __init__(self, visc=None, length=None, velocity=None, Re=None, freq=None):
        """Initializes the converter.

        :param visc: physical viscosity
        :param length: physical reference length
        :param velocity: physical reference velocity
        :param Re: Reynolds number
        :param freq: physical frequency [Hz]
        """
        self._phys_visc = visc
        self._phys_len = length
        self._phys_vel = velocity
        self._phys_freq = freq

        if Re is not None:
            if visc is None:
                self._phys_visc = length * velocity / Re
            elif length is None:
                self._phys_len = Re * visc / velocity
            elif velocity is None:
                self._phys_vel = Re * visc / length

        self._lb_visc = None
        self._lb_len = None
        self._lb_vel = None

    def set_lb(self, visc=None, length=None, velocity=None):
        if visc is not None:
            self._lb_visc = visc
        if length is not None:
            self._lb_len = length
        if velocity is not None:
            self._lb_vel = velocity

        self._update_missing_parameters()

    def _update_missing_parameters(self):
        if (self._lb_visc is None and self._lb_len is not None and
            self._lb_vel is not None):
            self._lb_visc = self._lb_len * self._lb_vel / self.Re
            assert self._lb_visc <= 1.0/6.0
            return

        if (self._lb_len is None and self._lb_visc is not None and
            self._lb_vel is not None):
            self._lb_len = self.Re * self._lb_visc / self._lb_vel
            return

        if (self._lb_vel is None and self._lb_len is not None and
            self._lb_visc is not None):
            self._lb_vel = self.Re * self._lb_visc / self._lb_len
            return

    @property
    def Re(self):
        return self._phys_len * self._phys_vel / self._phys_visc

    @property
    def Womersley(self):
        return math.sqrt(2 * math.pi * self._phys_freq * self._phys_len**2 / self._phys_visc)

    @property
    def Re_lb(self):
        return self._lb_len * self._lb_vel / self._lb_visc

    @property
    def Womersley_lb(self):
        return math.sqrt(2 * math.pi * self.freq_lb * self.len_lb**2 / self.visc_lb)

    @property
    def visc_lb(self):
        return self._lb_visc

    @property
    def velocity_lb(self):
        return self._lb_vel

    @property
    def len_lb(self):
        return self._lb_len

    @property
    def freq_lb(self):
        if self._phys_freq is None:
            return 1.0
        return self._phys_freq * self.dt

    @property
    def dx(self):
        if self._lb_len is None:
            return 0
        return self._phys_len / self._lb_len

    @property
    def dt(self):
        if self._lb_visc is None:
            return 0
        return self._lb_visc / self._phys_visc * self.dx**2

    @property
    def info_lb(self):
        return ('Re:%.2f  Wo:%.2f  visc:%.3e  vel:%.3e  len:%.3e  T:%d  '
                'dx:%.4e  dt:%.4e' % (
                    self.Re_lb, self.Womersley_lb, self.visc_lb, self.velocity_lb,
                    self.len_lb, int(1.0 / self.freq_lb), self.dx, self.dt))
