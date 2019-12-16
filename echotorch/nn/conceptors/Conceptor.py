# -*- coding: utf-8 -*-
#
# File : echotorch/nn/conceptors/Conceptor.py
# Description : Base conceptor class
# Date : 4th of November, 2019
#
# This file is part of EchoTorch.  EchoTorch is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Nils Schaetti <nils.schaetti@unine.ch>

"""
Created on 4 November 2019
@author: Nils Schaetti
"""

# Imports
import torch
from torch.autograd import Variable
import math

from ..NeuralFilter import NeuralFilter
from echotorch.utils.utility_functions import generalized_squared_cosine


# Conceptor base class
class Conceptor(NeuralFilter):
    """
    Conceptor base class
    """

    # Constructor
    def __init__(self, input_dim, aperture, *args, **kwargs):
        """
        Constructor
        :param input_dim: Conceptor dimension
        :param aperture: Aperture parameter
        :param args: Arguments
        :param kwargs: Propositional arguments
        """
        # Superclass
        super(Conceptor, self).__init__(
            input_dim=input_dim,
            output_dim=input_dim,
            *args,
            **kwargs
        )

        # Parameters
        self._aperture = aperture
        self._n_samples = 0
        c_size = input_dim

        # Initialize correlation matrix R
        self.register_buffer('R', Variable(torch.zeros(c_size, c_size, dtype=self._dtype), requires_grad=False))

        # Initialize Conceptor matrix C
        self.register_buffer('C', Variable(torch.zeros(c_size, c_size, dtype=self._dtype), requires_grad=False))
    # end __init__

    # region PROPERTIES

    # Get aperture
    @property
    def aperture(self):
        """
        Get aperture
        :return: Aperture
        """
        return self._aperture
    # end aperture

    # Change aperture
    @aperture.setter
    def aperture(self, ap):
        """
        Change aperture
        """
        self._aperture = ap
        self.update_C()
    # end aperture

    # Dimension
    @property
    def dim(self):
        """
        Dimension
        :return: Conceptor dimension
        """
        return self.C.size(0)
    # end dim

    # Singular values
    @property
    def SV(self):
        """
        Singular values
        :return: Singular values as a vector
        """
        (U, S, V) = torch.svd(self.C)
        return S
    # end SV

    # Singular values decomposition on C
    @property
    def SVD(self):
        """
        Singular values decomposition on C
        :return: Singular values as a vector
        """
        return torch.svd(self.C)
    # end SVD

    # Quota
    @property
    def quota(self):
        """
        Space occupied by C
        :return: Space occupied by C ([0, 1])
        """
        return float(torch.sum(self.SV) / self.input_dim)
    # end quota

    # endregion PROPERTIES

    # region PUBLIC

    # Get conceptor matrix
    def conceptor_matrix(self):
        """
        Get conceptor matrix
        """
        return self.C
    # end conceptor_matrix

    # Get correlation matrix
    def correlation_matrix(self):
        """
        Get correlation matrix
        """
        return self.R
    # end correlation_matrix

    # Filter signal
    def filter_fit(self, X, *args, **kwargs):
        """
        Filter signal
        :param X: Reservoir states
        """
        # Increment correlation matrices
        self._increment_correlation_matrices(X)
        return X
    # end filter_fit

    # Filter transform
    def filter_transform(self, X, *args, **kwargs):
        """
        Filter transform
        :param X: Input signal to filter
        :return: Filtered signal
        """
        return self.C.mv(X)
    # end filter_transform

    # Finalise
    def finalize(self):
        """
        Finalize training (learn C from R)
        """
        # Average R
        self.R /= self._n_samples

        # Compute Conceptor matrix C from R
        self.update_C()

        # Debug for C
        self._call_debug_point("C", self.C)

        # Out of training mode
        self.train(False)
    # end finalize

    # Reset
    def reset(self):
        """
        Reset
        :return:
        """
        # No samples
        self._n_samples = 0
        self.R.fill_(0.0)
        self.C.fill_(0.0)
    # end reset

    # Set correlation matrix
    def set_R(self, R, compute_C=True):
        """
        Set correlation matrix
        :param R: Correlation matrix
        """
        # New R
        self.R = R

        # New input
        self.input_dim = R.size(0)
        self.output_dim = R.size(0)

        # Update Conceptor matrix C
        if compute_C:
            self.update_C()
        # end if
    # end set_R

    # Set Conceptor matrix C
    def set_C(self, C, aperture, compute_R=True):
        """
        Set Conceptor matrix C
        :param C: Conceptor matrix C
        :param aperture: Conceptor's aperture
        """
        # New C
        self.C = C

        # New input / output dimensions
        self.input_dim = C.size(0)
        self.output_dim = C.size(0)

        # New aperture
        self._aperture = aperture

        # Update R
        if compute_R:
            self.update_R()
        # end if
    # end set_C

    # Update Conceptor matrix C
    def update_C(self):
        """
        Update Conceptor matrix C
        """
        self.C = Conceptor.computeC(self.R, self.aperture)
        self.train(False)
    # end update_C

    # Update correlation matrix R
    def update_R(self):
        """
        Update correlation matrix R
        """
        self.R = Conceptor.computeR(self.C, self.aperture)
        self.train(False)
    # end update_R

    # Multiply aperture by a factor
    def PHI(self, gamma):
        """
        Multiply aperture by a factor
        :param gamma: Multiply aperture by a factor.
        """
        # Dimension
        dim = self.dim

        # Multiply by 0
        if gamma == 0:
            (U, S, V) = torch.svd(self.C)
            Sdiag = S
            Sdiag[Sdiag < 1] = torch.zeros((sum(Sdiag < 1), 1))
            Cnew = torch.mm(U, torch.mm(torch.diag(Sdiag), U.t()))
        elif gamma == float("inf"):
            (U, S, V) = torch.svd(self.C)
            Sdiag = S
            Sdiag[Sdiag > 0] = torch.ones(sum(Sdiag > 0), 1)
            Cnew = torch.mm(U, torch.mm(torch.diag(Sdiag), U.t()))
        else:
            Cnew = torch.mm(self.C, torch.inverse(self.C + math.pow(gamma, -2) * (torch.eye(dim) - self.C)))
        # end

        # Set aperture and C
        self.set_C(Cnew, self._aperture * gamma)
    # end PHI

    # AND in Conceptor Logic
    def AND(self, B):
        """
        AND in Conceptor Logic
        :param B: Second conceptor operand (reservoir size x reservoir size)
        :return: Self AND B
        """
        # Dimension
        dim = self.input_dim
        tol = 1e-14

        # Conceptor matrices
        Cc = self.C
        Bc = B.C

        # Apertures
        C_aperture = self.aperture
        B_aperture = B.aperture

        # SV on both conceptor
        (UC, SC, UtC) = torch.svd(Cc)
        (UB, SB, UtB) = torch.svd(Bc)

        # Get singular values
        dSC = SC
        dSB = SB

        # How many non-zero singular values
        numRankC = int(torch.sum(1.0 * (dSC > tol)))
        numRankB = int(torch.sum(1.0 * (dSB > tol)))

        # Select zero singular vector
        UC0 = UC[:, numRankC:]
        UB0 = UB[:, numRankB:]

        # SVD on UC0 + UB0
        # (W, Sigma, Wt) = lin.svd(np.dot(UC0, UC0.T) + np.dot(UB0, UB0.T))
        (W, Sigma, Wt) = torch.svd(torch.mm(UC0, UC0.t()) + torch.mm(UB0, UB0.t()))

        # Number of non-zero SV
        numRankSigma = int(sum(1.0 * (Sigma > tol)))

        # Select zero singular vector
        Wgk = W[:, numRankSigma:]

        # C and B
        # Wgk * (Wgk^T * (C^-1 + B^-1 - I) * Wgk)^-1 * Wgk^T
        # CandB = Wgk @ torch.inverse(Wgk.t() @ (torch.pinverse(Cc, tol) + torch.pinverse(Bc, tol) - torch.eye(dim)) @ Wgk) @ Wgk.t()
        CandB = torch.mm(torch.mm(Wgk, torch.inverse(torch.mm(Wgk.t(), torch.mm((torch.pinverse(Cc, tol) + torch.pinverse(Bc, tol) - torch.eye(dim)), Wgk)))), Wgk.t())

        # New conceptor
        new_conceptor = Conceptor(
            input_dim=dim,
            aperture=1
        )

        # Cet C
        new_conceptor.set_C(
            C=CandB,
            aperture=1.0 / math.sqrt(math.pow(C_aperture, -2) + math.pow(B_aperture, -2))
        )

        return new_conceptor
    # end AND

    # AND in Conceptor Logic
    def AND_(self, B):
        """
        AND in Conceptor Logic
        :param B: Second conceptor operand (reservoir size x reservoir size)
        """
        # C AND B
        CandB = self.AND(B)
        self.set_C(CandB.C, CandB.aperture)
    # end AND_

    # OR in Conceptor Logic
    def OR(self, Q):
        """
        OR in Conceptor Logic
        :param Q: Second conceptor operand (reservoir size x reservoir size)
        :return: Self OR Q
        """
        # R OR Q
        return (self.NOT().AND(Q.NOT())).NOT()
    # end OR

    # OR in Conceptor Logic (in-place)
    def OR_(self, Q):
        """
        OR in Conceptor Logic (in-place)
        :param Q: Second operand Conceptor
        """
        newC = self.OR(Q)
        self.R = newC.R
        self._aperture = newC.aperture
        self.C = newC.C
    # end OR_

    # NOT
    def NOT(self):
        """
        NOT
        :return: ~C
        """
        # NOT correlation matrix
        not_C = torch.eye(self.input_dim) - self.C

        # New conceptor
        new_conceptor = Conceptor(
            input_dim=self.input_dim,
            aperture=1.0 / self._aperture
        )

        # Set R and C
        new_conceptor.set_C(not_C, aperture=1.0 / self._aperture, compute_R=True)

        return new_conceptor
    # end NOT

    # NOT (in-place)
    def NOT_(self):
        """
        NOT (in-place)
        """
        self.set_R(torch.eye(self.input_dim) - self.R)
    # end NOT_

    # Similarity
    def sim(self, other, based_on='C', sim_func=generalized_squared_cosine):
        """
        Generalized Cosine Similarity
        :param other: Second operand
        :param based_on: Similarity based on C ('C') or R ('R)
        :param sim_func: Similarity function (default: generalized_squared_cosine)
        :return: Similarity between self and other ([0, 1])
        """
        return Conceptor.similarity(self, other, based_on, sim_func)
    # end sim

    # Delta measure (sensibility of Frobenius norm to change of aperture)
    def delta(self, gamma, epsilon=0.01):
        """
        Delta measure (sensibility of Frobenius norm to change of aperture)
        :param gamma: Gamma
        :param epsilon: Epsilon
        :return: Delta measure
        """
        return Conceptor.delta_measure(self, gamma, epsilon)
    # end delta

    # Evidence (how X fits in Conceptor ellipsoid)
    def E(self, x):
        """
        Evidence (how X fits in Conceptor ellipsoid)
        :param x: Reservoir states
        :return:
        """
        return Conceptor.evidence(self, x)
    # end E

    # Make a copy of the conceptor
    def copy(self):
        """
        Make a copy of the conceptor
        """
        new_C = Conceptor(self.input_dim, self.aperture)
        new_C.set_R(self.R, compute_C=False)
        new_C.set_C(self.C, self.aperture, compute_R=False)
        return new_C
    # end copy

    # endregion PUBLIC

    # region PRIVATE

    # Increment correlation matrices
    def _increment_correlation_matrices(self, X):
        """
        Increment correlation matrices
        :param X: Reservoir states
        """
        if X.ndim == 3:
            # Learn length
            learn_length = X.size(1)

            # Batch size
            batch_size = X.size(0)

            # Increment R for each sample
            for batch_i in range(batch_size):
                # CoRrelation matrix of reservoir states
                self.R += (torch.mm(X[batch_i].t(), X[batch_i])) / float(learn_length)

                # Inc. n samples
                self._n_samples += 1
            # end for
        elif X.ndim == 2:
            # Learn length
            learn_length = X.size(0)

            # CoRrelation matrix of reservoir states
            self.R += (torch.mm(X.t(), X)) / float(learn_length)

            # Inc. n samples
            self._n_samples += 1
        elif X.ndim == 0:
            # CoRrelation matrix of reservoir states
            self.R += (torch.mm(X, X.t()))

            # Inc. n samples
            self._n_samples += 1
        else:
            raise Exception("Unknown number of dimension for states (X) {}".format(X.size()))
        # end if
    # end _increment_correlation_matrices

    # endregion PRIVATE

    # region OVERRIDE

    # Extra-information
    def extra_repr(self):
        """
        Extra-information
        :return: String
        """
        s = super(Conceptor, self).extra_repr()
        s += ', aperture={_aperture}'
        return s.format(**self.__dict__)
    # end extra_repr

    # endregion OVERRIDE

    # region OPERATORS

    # Equal operator
    # TODO: Test
    def __eq__(self, other):
        """
        Equal operator
        :param other:
        :return:
        """
        return self.C == other.C and self.aperture == other.aperture
    # end __eq__

    # Greater than (abstraction relationship)
    # TODO: Test
    def __gt__(self, other):
        """
        Greater than (abstraction relationship
        :param other: Second operand
        :return: True/False
        """
        # Eigen values of C - D
        eigv = torch.eig(other.C - self.C, eigenvectors=False)
        return float(torch.max(eigv)) > 0.0
    # end __gt__

    # Greater or equal (abstraction relationship)
    # TODO: Test
    def __ge__(self, other):
        """
        Greater or equal (abstraction relationship)
        :param other: Second operand
        :return: True/False
        """
        # Eigen values of C - D
        eigv = torch.eig(other.C - self.C, eigenvectors=False)
        return float(torch.max(eigv)) >= 0.0
    # end __ge__

    # Less than (abstraction relationship)
    # TODO: Test
    def __lt__(self, other):
        """
        Less than (abstraction relationship)
        :param other: Second operand
        :return: True/False
        """
        # Eigen value of C - D
        eigv = torch.eig(other.C - self.C, eigenvectors=False)
        return float(torch.max(eigv)) < 0.0
    # end __lt__

    # Less or equal than (abstraction relationship)
    # TODO: Test
    def __le__(self, other):
        """
        Less or equal than (abstraction relatioship)
        :param other: Second operand
        :return: True/False
        """
        eigv = torch.eig(other.C - self.C, eigenvectors=False)
        return float(torch.max(eigv)) <= 0.0
    # end __le__

    # Addition (+)
    # TODO: Test
    def __add__(self, other):
        """
        Addition
        :param other: Second operand
        :return: self + other
        """
        # New Conceptor
        CplusB = Conceptor(self.input_dim, 1.0)

        # Set Conceptor matrix C
        # TODO: Check how aperture behave under C addition
        CplusB.set_C(self.C + other.C, 1.0)
        return CplusB
    # end __add__

    # Substraction (-)
    # TODO: Test
    def __sub__(self, other):
        """
        Substraction (-)
        :param other: Second operand
        :return: self - other
        """
        # New Conceptor
        CsubB = Conceptor(self.input_dim, 1.0)

        # Set Conceptor matrix C
        # TODO: Check how aperture behave under C substraction
        CsubB.set_C(self.C - other.C, 1.0)
        return CsubB
    # end __sub__

    # Right multiplication (other * C)
    # TODO: Test
    def __rmul__(self, other):
        """
        Right multiplication (other * C)
        :param other: Second operand
        :return: other * C
        """
        # Copy this conceptor
        new_C = self.copy()

        # Multiply
        # TODO: Check how aperture behave under C multiplication
        new_C.set_C(self.C * other, 1.0)

        return new_C
    # end __rmul__

    # Left multiplication (C * other)
    # TODO: Test
    def __mul__(self, other):
        """
        Left multiplication (C * other)
        :param other: Second operand
        :return: C * other
        """
        # Copy this conceptor
        new_C = self.copy()

        # Multiply
        # TODO: Check how aperture behave under C multiplication
        new_C.set(self.C * other, 1.0)

        return new_C
    # end __mul__

    # endregion OPERATORS

    # region STATIC

    # NOT operator
    @staticmethod
    def operator_NOT(C):
        """
        NOT operator
        :param C: Conceptor matrix
        :return: NOT version of R
        """
        return C.NOT()
    # end operator_NOT

    # OR in Conceptor Logic
    @staticmethod
    def operator_OR(C, B):
        """
        OR in Conceptor Logic
        :param C: First Conceptor operand (reservoir size x reservoir size)
        :param B: Second Conceptor operand (reservoir size x reservoir size)
        :return: C OR B
        """
        # C OR B
        return C.OR(B)
    # end operator_OR

    # AND in Conceptor Logic
    @staticmethod
    def operator_AND(C, B):
        """
        AND in Conceptor Logic
        :param C: First Conceptor operand
        :param B: Second Conceptor operand
        :return: C AND B
        """
        # C AND B
        return C.AND(B)
    # end operator_AND

    # PHI in Conceptor Logic
    @staticmethod
    def operator_PHI(C, gamma):
        """
        PHI in Conceptor Logic
        :param C: Conceptor object
        :param gamma: Aperture multiplication parameter
        :return: Scaled conceptor
        """
        return C.PHI(gamma)
    # end operator_PHI

    # Compute C from correlation matrix R
    # TODO: Test
    @staticmethod
    def computeC(R, aperture, inv_algo=torch.inverse):
        """
        Compute C from correlation matrix R
        :param R: Correlation matrix
        :param aperture: Aperture parameter
        :param inv_algo: Matrix inversion function (default: torch.inv)
        :return: C matrix (as torch tensor)
        """
        R_dim = R.size(0)
        return torch.mm(inv_algo(R + math.pow(aperture, -2) * torch.eye(R_dim)), R)
    # end computeC

    # Compute R from conceptor matrix C
    # TODO: Test
    @staticmethod
    def computeR(C, aperture, inv_algo=torch.inverse):
        """
        Compute R from conceptor matrix C
        :param C: Conceptor matrix C
        :param aperture: Aperture parameter
        :param inv_algo: Matrix inversion function (default: torch.inv)
        :return: R matrix (as torch tensor)
        """
        C_dim = C.size(0)
        return math.pow(aperture, -2) * torch.mm(C, inv_algo(torch.eye(C_dim) - C))
    # end R

    # Return empty conceptor
    # TODO: Test
    @staticmethod
    def empty(input_dim):
        """
        Return an empty conceptor
        :param input_dim: Conceptor dimension
        :return: Empty conceptor (zero)
        """
        return Conceptor.min(input_dim)
    # end empty

    # Return identity conceptor
    # TODO: Test
    @staticmethod
    def identity(input_dim):
        """
        Return identity conceptor (no filtering)
        :param input_dim: Input dimension
        :return: Identity conceptor
        """
        return Conceptor.max(input_dim)
    # end identity

    # Global minimal element
    # TODO: Test
    @staticmethod
    def min(input_dim):
        """
        Global minimal element
        :param input_dim: Conceptor dimension
        :return: Global minimal element (with 0 as C matrix)
        """
        # GME conceptor
        return Conceptor(input_dim, aperture=0.0)
    # end min

    # Global maximal element
    # TODO: Test
    @staticmethod
    def max(input_dim):
        """
        Global maximal element
        :param input_dim: Conceptor dimension
        :return: Global maximal element (with I as C matrix)
        """
        # GME conceptor
        gme = Conceptor(input_dim, aperture=1.0)
        gme.set_C(torch.eye(input_dim), 1.0)
        return gme
    # end max

    # Similarity between conceptors
    # TODO: Test
    @staticmethod
    def similarity(c1, c2, based_on='C', sim_func=generalized_squared_cosine):
        """
        Similarity between conceptors
        :param c1: First conceptor
        :param c2: Second conceptor
        :param based_on: Similarity based on C ('C') or R ('R)
        :param sim_func: Similarity function
        :return: Similarity
        """
        # Compute singular values
        # Ua, Sa, _ = torch.svd(c1.C)
        # Ub, Sb, _ = torch.svd(c2.C)

        # Measure
        # return sim_func(Sa, Ua, Sb, Ub)
        if based_on == 'C':
            return sim_func(c1.C, c2.C)
        else:
            return sim_func(c1.R, c2.R)
    # end sim

    # Delta measure (sensibility of Frobenius norm to change of aperture)
    # TODO: Test
    @staticmethod
    def delta_measure(self, C, gamma, epsilon=0.01):
        """
        Delta measure (sensibility of Frobenius norm to change of aperture)
        :param C: Conceptor object
        :param gamma: Gamma
        :param epsilon: Epsilon
        :return: Delta measure
        """
        # Conceptors with two gammas
        A = Conceptor.operator_PHI(C, gamma - epsilon)
        B = Conceptor.operator_PHI(C, gamma + epsilon)

        # Gradient of Frobenius norm
        A_norm = math.pow(torch.norm(A, p=2), 2)
        B_norm = math.pow(torch.norm(B, p=2), 2)
        d_C_norm = B_norm - A_norm

        # Change in log (gamma)
        d_log_gamma = torch.log(gamma + epsilon) - torch.log(gamma - epsilon)
        return d_C_norm / d_log_gamma, d_C_norm
    # end delta

    # How x fits in Conceptor ellipsoid (Evidence)
    # TODO: Test
    @staticmethod
    def evidence(C, x):
        """
        How x fits in Conceptor ellipsoid (Evidence)
        :param C: Conceptor object
        :param x: Reservoir states
        :return:
        """
        return x.mm(C.C).mm(x.t())
    # end E

    # endregion STATIC

# end Conceptor
