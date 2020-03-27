#!/usr/bin/env python

"""
    PyLDM - Lifetime Density Analysis
    Copyright (C) 2016 Gabriel Dorlhiac, Clyde Fare

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

 """

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize
from scipy.linalg import *
from scipy.special import erf
from matplotlib.widgets import Slider
from .discreteslider import DiscreteSlider

class SVD_GA(object):
    def __init__(self, data):
        self.updateData(data)
        
    def updateData(self, data):
        self.U, self.S, self.Vt = data.get_SVD()
        self.Svals = self.S
        self.S = np.diag(self.S)
        self.wLSV = self.U.dot(self.S)
        self.T = data.get_T()
        self.wls = data.get_wls()
        self.chirporder, self.FWHM, self.munot, self.mu, self.lamnot = data.get_IRF()
        self.FWHM_mod = self.FWHM/(2*np.log(2)**0.5)

    def display(self):
        fig = plt.figure()
        fig.canvas.set_window_title('Singular Values')
        ax = fig.add_subplot(121)
        ax.plot(range(1,len(self.Svals)+1), self.Svals, 'o-')
        ax2 = fig.add_subplot(122)
        plt.subplots_adjust(left=0.25, bottom=0.25)
        ax2.plot(self.T, self.wLSV[:,0], 'bo-', label='wLSV 1')
        plt.xscale('log')
        plt.legend(loc=0, frameon=False)
        axS = plt.axes([0.25, 0.1, 0.65, 0.03])
        self.S = Slider(axS, 'wLSV', 1, len(self.wLSV[0]), valinit=1, valfmt='%0.0f')
        def update(val):
            n = int(self.S.val)
            ax2.clear()
            ax2.plot(self.T, self.wLSV[:,n-1], 'bo-', label='wLSV %d'%n)
            ax2.set_xscale('log')
            ax2.legend(loc=0, frameon=False)
            plt.draw()
        self.S.on_changed(update)

    def _genD(self, taus, T, fit_irf):
        if fit_irf:
            D = np.zeros([len(T), len(taus)-1]) # Because FWHM is a fit parameter, passed as the last item in taus
            fwhm = taus[-1]
            fwhm_mod = fwhm/(2*sqrt(log(2)))
        else:
            D = np.zeros([len(T), len(taus)])
        for i in range(len(D)):
            for j in range(len(D[i])):
                t = T[i]
                tau = taus[j]
                if fit_irf:
                    One = 0.5*(np.exp(-t/tau)*exp(fwhm_mod**2/(2*tau))/tau)
                    Two = 1 + erf((t-(fwhm_mod**2/tau))/(sqrt(2)*fwhm_mod))
                    D[i, j] = One*Two
                else:
                    if self.FWHM_mod != 0:
                        One = 0.5*(np.exp(-t/tau)*exp(self.FWHM_mod**2/(2*tau))/tau)
                        Two = 1 + erf((t-(self.FWHM_mod**2/tau))/(sqrt(2)*self.FWHM_mod))
                        D[i, j] = One*Two
                    else:
                        D[i, j] = np.exp(-t/tau)
        return D
        
    def _getDAS(self, D, Y, alpha=0):
        if alpha != 0:
            D_aug = np.concatenate((D, alpha**(0.5)*np.identity(len(D[0]))))
            Y_aug = np.concatenate((Y, np.zeros([len(D_aug[0]), len(Y[0])])))
        else:
            D_aug = D
            Y_aug = Y
        Q, R = np.linalg.qr(D_aug)
        Qt = np.transpose(Q)
        DAS = np.zeros([len(D_aug[0]),len(Y_aug[0])])
        QtY = Qt.dot(Y_aug)
            
        DAS[-1, :] = QtY[-1, :]/R[-1, -1]
        for i in range(len(DAS)-2, -1, -1):
            s = 0
            for k in range(i+1, len(DAS)):
                s += R[i, k]*DAS[k, :]
                DAS[i, :] = (QtY[i, :] - s)/R[i, i]
        return DAS

    def _min(self, taus, Y, T, alpha, fit_irf):
        D = self._genD(taus, T, fit_irf)
        DAS = self._getDAS(D, Y, alpha)
        res = np.sum((Y - D.dot(DAS))**2)
        return res

    def _GA(self, x0, Y, T, alpha, B, fit_irf):
        result = minimize(self._min, x0, args=(Y, T, alpha, fit_irf), bounds=B)
        taus = result.x
        D = self._genD(taus, T, fit_irf)
        DAS = self._getDAS(D, Y, alpha)
        return taus, DAS, D.dot(DAS)

    def Global(self, wLSVs, x0, B, alpha, fit_irf=False, fwhm=None):
        wLSV_indices, wLSV_fit = self._get_wLSVs_for_fit(wLSVs, B)
        print('Singular vectors for fit: {}'.format(wLSV_indices))
        taus, DAS, SpecFit = self._GA(x0, wLSV_fit, self.T, alpha, B, fit_irf)
        print('Fitted lifetimes: {}'.format(taus))
        if fit_irf:
            self._plot_res(wLSV_fit, wLSV_indices, taus[:-1], DAS, SpecFit, self.T)
            fwhm = taus[-1]
            return taus[:-1], fwhm
        self._plot_res(wLSV_fit, wLSV_indices, taus, DAS, SpecFit, self.T)
        return taus

    def _get_wLSVs_for_fit(self, wLSV_indices, B):
        wLSV_indices = wLSV_indices.split()
        if wLSV_indices: # List as condition returns true if not empty
            wLSV_indices = list(map(int, wLSV_indices))
            if wLSV_indices is None:
                if B is not None:
                    wLSV_fit = self.wLSV[:, :len(B)]
                else:
                    wLSV_fit = self.wLSV[:, :3]
            elif len(wLSV_indices) == 1:
                wLSV_fit = self.wLSV[:, :wLSV_indices[0]]
            else:
                wLSV_fit = np.zeros([len(self.T), len(wLSV_indices)])
                for j in range(len(wLSV_indices)):
                    wLSV_fit[:, j] = self.wLSV[:, wLSV_indices[j]-1]
        else:
            wLSV_indices = [3]
            wLSV_fit = self.wLSV[:, :wLSV_indices[0]]
        return wLSV_indices, wLSV_fit
        
    def _plot_res(self, wLSV_fit, wLSVs, taus, DAS, SpecFit, T):
        if len(wLSVs) == 1:
            wLSVs = range(1, wLSVs[0]+1)
        fig = plt.figure()
        fig.canvas.set_window_title('GA Fits')
        plt.subplots_adjust(left=0.25, bottom=0.25)
        ax = fig.add_subplot(121)
        for i in range(len(DAS)):
            ax.plot(range(1, len(DAS[0])+1), DAS[i, :], label="%.3f"%taus[i])
        ax.legend(loc=0, frameon=False)

        ax2 = fig.add_subplot(122)
        ax2.plot(T, wLSV_fit[:,0], 'bo-', label='wLSV 1')
        ax2.plot(T, SpecFit[:,0], 'r', label='Fit')
        ax2.set_xscale('symlog', linthreshy=1)
        ax2.legend(loc=0, frameon=False)
        axS = plt.axes([0.25, 0.1, 0.65, 0.03])
        self.S = DiscreteSlider(axS, 'wLSV', 1, len(taus)+1, valinit=1, valfmt='%0.0f', increment=1)
        def update(val):
            n = int(self.S.val)
            ax2.clear()
            ax2.plot(T, wLSV_fit[:,n-1], 'bo-', label='wLSV %d'%wLSVs[n-1])
            ax2.plot(T, SpecFit[:,n-1], 'r', label='Fit')
            ax2.set_xscale('symlog', linthreshy=1)
            ax2.legend(loc=0, frameon=False)
            plt.draw()
        self.S.on_changed(update)
